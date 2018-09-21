import os
import re
from logging import getLogger
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

import requests
from celery import group, task
from django.conf import settings

from concordia.models import Project
from importer.models import CampaignItemAssetCount, CampaignTaskDetails

logger = getLogger(__name__)


def get_item_id_from_item_url(item_url):
    """
    extracts item id from the item url and returns it
    :param item_url: item url
    :return: item id
    """
    if item_url.endswith("/"):
        item_id = item_url.split("/")[-2]
    else:
        item_id = item_url.split("/")[-1]

    return item_id


def normalize_collection_url(original_url):
    """
    Given a P1 collection/search URL, produce a normalized version which is safe
    to import. This will replace parameters related to our response format and
    pagination requirements but otherwise leave the query string unmodified.
    """

    parsed_url = urlsplit(original_url)

    new_qs = [("fo", "json")]

    for k, v in parse_qsl(parsed_url.query):
        if k not in ("fo", "at", "sp"):
            new_qs.append((k, v))

    return urlunsplit(
        (parsed_url.scheme, parsed_url.netloc, parsed_url.path, urlencode(new_qs), None)
    )


def get_collection_items(collection_url):
    """
    :param collection_url: URL of a loc.gov collection or search results page
    :return: list of (item_id, item_url) tuples
    """

    items = []
    current_page_url = collection_url

    while current_page_url:
        resp = requests.get(current_page_url)
        resp.raise_for_status()
        data = resp.json()

        if "results" not in data:
            logger.error('Expected URL %s to include "results"', resp.url)
            continue

        for result in data["results"]:
            try:
                item_info = get_item_info_from_result(result)
            except Exception as exc:
                logger.warning(
                    "Skipping result from %s which did not match expected format: %s",
                    resp.url,
                    exc,
                    exc_info=True,
                    extra={"data": {"result": result, "url": resp.url}},
                )
                continue

            if item_info:
                items.append(item_info)

        current_page_url = data["pagination"].get("next", None)

    if not items:
        logger.warning("No valid items found for collection url: %s", collection_url)

    return items


def get_item_info_from_result(result):
    """
    Given a P1 result, return the item ID and URL if it represents a collection
    item

    :return: (item_id, item_url) tuple or None if the URL does not represent a
             supported item type
    """

    ignored_formats = {"collection", "web page"}

    item_id = result["id"]
    original_format = result["original_format"]

    if ignored_formats.intersection(original_format):
        logger.info(
            "Skipping result %s because it contains an unsupported format: %s",
            item_id,
            original_format,
            extra={"data": {"result": result}},
        )
        return

    image_url = result.get("image_url")
    if not image_url:
        logger.info(
            "Skipping result %s because it lacks an image_url",
            item_id,
            extra={"data": {"result": result}},
        )
        return

    item_url = result["url"]

    m = re.search(r"loc.gov/item/([^/]+)", item_url)
    if not m:
        logger.info(
            "Skipping %s because the URL %s doesn't appear to be an item!",
            item_id,
            item_url,
            extra={"data": {"result": result}},
        )
        return

    return m.group(1), item_url


def get_campaign_item_asset_urls(item_id):
    """
    :param item_id: campaign item id
    :return: item asset urls
    """
    campaign_item_asset_urls = []
    item_url = "https://www.loc.gov/item/{0}/".format(item_id)
    resp = requests.get(item_url, {"fo": "json"})
    resp.raise_for_status()
    campaign_item_data = resp.json()

    item_resources = campaign_item_data.get("resources", [])

    for ir in item_resources:
        item_files = ir.get("files", [])
        for item_file in item_files:
            similar_img_urls = []
            for itf in item_file:
                if itf.get("mimetype") == "image/jpeg":
                    similar_img_urls.append(itf.get("url"))
            if similar_img_urls:
                campaign_item_asset_urls.append(similar_img_urls[-1])

    return campaign_item_asset_urls


def import_items_into_project_from_url(project, import_url):
    """
    Given a loc.gov URL, return the task ID for the import task
    """

    parsed_url = urlparse(import_url)

    if re.match(r"^/(collections|search)/", parsed_url.path):
        return download_write_campaign_item_assets.delay(project.pk, import_url)
    elif re.match(r"^/(item)/", parsed_url.path):
        return download_write_item_assets.delay(project.pk, import_url)
    else:
        raise ValueError(
            f"{import_url} doesn't match one of the known importable patterns"
        )


def download_write_campaign_item_asset(image_url, asset_local_path):
    """
    :param image_url:
    :param asset_local_path:
    """

    try:
        resp = requests.get(image_url, stream=True)
        resp.raise_for_status()

        with open(asset_local_path, "wb") as fd:
            for chunk in resp.iter_content(chunk_size=256 * 1024):
                fd.write(chunk)
    except Exception as e:
        logger.error(
            "Error while saving %s to %s: %s",
            image_url,
            asset_local_path,
            e,
            exc_info=True,
            extra={
                "data": {"image_url": image_url, "local filename": asset_local_path}
            },
        )


def get_save_item_assets(project, item_id, item_asset_urls):
    """
    creates a item directory if it already does not exists, and iterates asset
    urls list then download each asset and saves to local in item directory

    :param campaign_name: campaign_name
    :param item_id: item id of the campaign
    :param item_asset_urls: list of item asset urls
    :return: nothing, it will download the assets to local path
    """

    item_local_path = os.path.join(
        settings.IMPORTER["IMAGES_FOLDER"], project.campaign.slug, project.slug, item_id
    )

    os.makedirs(item_local_path, exist_ok=True)

    for idx, ciau in enumerate(item_asset_urls, start=1):
        asset_local_path = os.path.join(item_local_path, "{}.jpg".format(idx))

        try:
            download_write_campaign_item_asset(ciau, asset_local_path)
        except Exception as exc:
            # FIXME: determine whether we can reliably recover from this condition
            logger.error(
                "Unable to save asset for campaign %s project %s item %s: %s",
                project.campaign.title,
                project.title,
                item_id,
            )
            raise


@task(bind=True)
def download_write_campaign_item_assets(self, project_id, original_collection_url):
    """
    Download images from a loc.gov collection or search page into a local
    directory under a campaign/project hierarchy

    :param project_id: primary key for a concordia.Project instance
    :param collection_url: collection or search results URL
    :return: nothing
    """

    # To avoid stale data we pass the project ID rather than the serialized object:
    project = Project.objects.get(pk=project_id)

    # We'll split the URL parameters
    collection_url = normalize_collection_url(original_collection_url)
    collection_items = get_collection_items(collection_url)

    ctd = CampaignTaskDetails()
    ctd.project = project
    ctd.campaign_task_id = self.request.id
    ctd.campaign_item_count = len(collection_items)
    ctd.save()

    # FIXME: add a parent/child task tracking field
    item_group = group(
        download_write_item_assets.s(project.pk, item_url)
        for item_id, item_url in collection_items
    )
    return item_group()


@task(bind=True)
def download_write_item_assets(self, project_id, item_url):
    """
    Download images from a loc.gov item into a local directory under a
    campaign/project hierarchy

    :param project_id: primary key for a concordia.Project instance
    :param item_url: item URL
    :return: nothing
    """

    # To avoid stale data we pass the project ID rather than the serialized object:
    project = Project.objects.get(pk=project_id)

    item_id = get_item_id_from_item_url(item_url)

    item_asset_urls = get_campaign_item_asset_urls(item_id)

    ctd = CampaignTaskDetails()
    ctd.project = project
    ctd.campaign_item_count += 1
    ctd.campaign_asset_count += len(item_asset_urls)
    ctd.campaign_task_id = self.request.id
    ctd.full_clean()
    ctd.save()

    ciac = CampaignItemAssetCount()
    ciac.item_task_id = self.request.id
    ciac.campaign_task = ctd
    ciac.campaign_item_identifier = item_id
    ciac.campaign_item_asset_count = len(item_asset_urls)
    ciac.full_clean()
    ciac.save()

    get_save_item_assets(project, item_id, item_asset_urls)

    item, created = project.item_set.get_or_create(
        item_id=item_id,
        defaults={"title": item_id, "slug": item_id, "campaign": project.campaign},
    )

    item_local_path = os.path.join(
        settings.IMPORTER["IMAGES_FOLDER"], project.campaign.slug, project.slug, item_id
    )

    # FIXME: remove this import once the code is cleaned up
    from .views import save_campaign_item_assets

    save_campaign_item_assets(project, item_local_path, item_id)

    import shutil

    shutil.rmtree(
        os.path.join(
            settings.IMPORTER["IMAGES_FOLDER"], project.campaign.slug, project.slug
        )
    )
