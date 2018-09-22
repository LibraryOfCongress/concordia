"""
See the module-level docstring for implementation details
"""

import os
import re
from logging import getLogger
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlsplit, urlunsplit

import requests
from celery import group, task
from django.conf import settings
from django.db.transaction import atomic
from django.template.defaultfilters import slugify
from django.utils.timezone import now
from requests.exceptions import HTTPError

from concordia.models import Asset, MediaType, Project
from importer.models import ImportItemAsset, ImportJob

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


def import_items_into_project_from_url(requesting_user, project, import_url):
    """
    Given a loc.gov URL, return the task ID for the import task
    """

    parsed_url = urlparse(import_url)

    m = re.match(r"^/(collections|search|item)/", parsed_url.path)
    if not m:
        raise ValueError(
            f"{import_url} doesn't match one of the known importable patterns"
        )
    url_type = m.group(1)

    import_job = ImportJob(
        project=project, created_by=requesting_user, source_url=import_url
    )
    import_job.full_clean()
    import_job.save()

    if url_type == "item":
        import_item.delay(import_job.pk, import_url)
    else:
        # Both collections and search results return the same format JSON
        # reponse so we can use the same code to process them:
        import_collection.delay(import_job.pk)

    return import_job


@task(bind=True)
@atomic
def import_item(self, import_job_pk, item_url):
    import_job = ImportJob.objects.get(pk=import_job_pk)

    if import_job.completed or import_job.failed:
        logger.warning("Not reprocessing finalized %s", import_job)
        return

    # Update metadata:
    import_job.task_id = self.request.id
    import_job.save()

    item, created = import_job.project.item_set.get_or_create(
        item_url=item_url,
        campaign=import_job.project.campaign,
        project=import_job.project,
    )
    if not created:
        import_job.status = "Not reprocessing existing item %s" % item
        import_job.completed = now()
        import_job.full_clean()
        import_job.save()

        return

    import_item, created = import_job.items.get_or_create(url=item_url, item=item)

    # Load the Item record with metadata from the remote URL:

    resp = requests.get(item_url, params={"fo": "json"})
    resp.raise_for_status()
    item_data = resp.json()

    populate_item_from_url(item, item_data["item"])

    item_assets = []
    import_assets = []
    for idx, asset_url in enumerate(
        get_asset_urls_from_item_resources(item_data.get("resources", [])), start=1
    ):
        asset_title = f"{item.item_id}-{idx}"
        item_asset = Asset(
            project=import_job.project,
            campaign=import_job.project.campaign,
            item=item,
            title=asset_title,
            slug=slugify(asset_title),
            sequence=idx,
            media_url="{idx}.jpg",
            media_type=MediaType.IMAGE,
            download_url=asset_url,
        )
        item_asset.full_clean()
        item_assets.append(item_asset)

    Asset.objects.bulk_create(item_assets)

    for asset in item_assets:
        import_asset = ImportItemAsset(
            import_item=import_item,
            asset=asset,
            url=asset.download_url,
            sequence_number=asset.sequence,
        )
        import_asset.full_clean()
        import_assets.append(import_asset)

    import_item.assets.bulk_create(import_assets)

    download_asset_group = group(download_asset.s(i) for i in import_assets)

    import_item.full_clean()
    import_item.save()

    return download_asset_group()


@task(bind=True)
def import_collection(self, import_job_pk):
    raise NotImplementedError


def populate_item_from_url(item, item_info):
    """
    Populates a Concordia.Item from the provided loc.gov URL

    Returns the retrieved JSON data so additional imports can be peformed
    without a second request
    """

    item.item_id = get_item_id_from_item_url(item_info["id"])

    for k in ("title", "description"):
        v = item_info.get(k)
        if v:
            setattr(item, k, v)

    if not item.slug:
        item.slug = slugify(item.title)

    # FIXME: this was never set before so we don't have selection logic:
    thumb_urls = [i for i in item_info["image_url"] if ".jpg" in i]
    if thumb_urls:
        item.thumbnail_url = urljoin(item.item_url, thumb_urls[0])

    item.full_clean()
    item.save()


def get_asset_urls_from_item_resources(resources):
    """
    Given a loc.gov JSON response, return the list of asset URLs matching our
    criteria (JPEG, largest version available)
    """

    assets = []

    for resource in resources:
        # The JSON response for each file is a list of available image versions
        # we will attempt to save the highest resolution JPEG:

        for item_file in resource.get("files", []):
            candidates = []

            for variant in item_file:
                if any(i for i in ("url", "height", "width") if i not in variant):
                    continue

                url = variant["url"]
                height = variant["height"]
                width = variant["width"]

                if variant.get("mimetype") == "image/jpeg":
                    candidates.append((url, height * width))

            if candidates:
                candidates.sort(key=lambda i: i[1], reverse=True)
                assets.append(candidates[0][0])

    return assets


def download_image(image_url, asset_local_path):
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


def download_item_assets(project, item_id, item_asset_urls):
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
            download_image(ciau, asset_local_path)
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

    # FIXME: add a parent/child task tracking field
    item_group = group(
        download_item_assets.s(project.pk, item_url)
        for item_id, item_url in collection_items
    )
    return item_group()


@task(
    bind=True,
    autoretry_for=(HTTPError,),
    retry_backoff=True,
    retry_backoff_max=8 * 60 * 60,
    retry_jitter=True,
    retry_kwargs={"max_retries": 12},
)
def download_item_assets(self, project_id, item_url):
    """
    Download images from a loc.gov item into a local directory under a
    campaign/project hierarchy

    :param project_id: primary key for a concordia.Project instance
    :param item_url: item URL
    :return: nothing
    """
    raise NotImplementedError
    # To avoid stale data we pass the project ID rather than the serialized object:
    project = Project.objects.get(pk=project_id)

    item_id = get_item_id_from_item_url(item_url)

    item_asset_urls = get_asset_urls_for_item(item_id)

    download_item_assets(project, item_id, item_asset_urls)

    item, created = project.item_set.get_or_create(
        item_id=item_id,
        defaults={"title": item_id, "slug": item_id, "campaign": project.campaign},
    )
    if not created:
        logger.info("Won't re-import item %s", item)
        return

    item_local_path = os.path.join(
        settings.IMPORTER["IMAGES_FOLDER"], project.campaign.slug, project.slug, item_id
    )

    # FIXME: remove this import once the code is cleaned up
    from .views import save_campaign_item_assets

    save_campaign_item_assets(project, item_local_path, item_id)

    import shutil

    shutil.rmtree(
        os.path.join(
            settings.IMPORTER["IMAGES_FOLDER"],
            project.campaign.slug,
            project.slug,
            item_id,
        )
    )
