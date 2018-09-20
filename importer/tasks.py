import os
import re
from urllib.parse import urlparse
from collections import defaultdict
from logging import getLogger

import requests
from celery import task
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


def get_campaign_pages(campaign_url):
    """
    Return total pages in given loc gov campaign urls
    :param campaign_url:
    :return: int total no of pages
    """

    resp = requests.get(campaign_url, params={"fo": "json", "at": "pagination"})
    resp.raise_for_status()
    data = resp.json()

    total_pages = data.get("pagination", {}).get("total", 0)
    logger.info(
        "total_campaign_pages: %s for campaign url: %s", total_pages, campaign_url
    )
    return total_pages


def get_campaign_item_ids(campaign_url, total_pages):
    """
    :param campaign_url: campaign url
    :param total_pages: number of pages in this campaign url
    :return: list of campaign of item ids
    """
    campaign_item_ids = []
    for page_num in range(1, total_pages + 1):
        resp = requests.get(campaign_url, params={"fo": "json", "at": "results"})
        resp.raise_for_status()
        data = resp.json()

        page_results = data.get("results", [])

        for pr in page_results:
            if (
                pr.get("id")
                and pr.get("image_url")
                and "campaign" not in pr.get("original_format")
                and "web page" not in pr.get("original_format")
            ):
                campaign_item_url = pr.get("id")
                campaign_item_ids.append(campaign_item_url.split("/")[-2])

    if not campaign_item_ids:
        logger.info("No item ids found for campaign url: %s", campaign_url)

    return campaign_item_ids


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
        task_id = download_write_campaign_item_assets.delay(project.pk, import_url)
    elif re.match(r"^/(item)/", parsed_url.path):
        task_id = download_write_item_assets.delay(project.pk, import_url)
    else:
        raise ValueError(
            f"{import_url} doesn't match one of the known importable patterns"
        )

    return task_id


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


@task
def download_write_campaign_item_assets(project_id, collection_url):
    """
    Download images from a loc.gov collection or search page into a local
    directory under a campaign/project hierarchy

    :param project_id: primary key for a concordia.Project instance
    :param collection_url: collection or search results URL
    :return: nothing
    """

    # To avoid stale data we pass the project ID rather than the serialized object:
    project = Project.objects.get(pk=project_id)

    total_pages = get_campaign_pages(collection_url)
    collection_item_ids = get_campaign_item_ids(collection_url, total_pages)
    items_asset_count_dict = defaultdict(int)
    items_assets = {}

    for cii in collection_item_ids:
        campaign_item_asset_urls = get_campaign_item_asset_urls(cii)
        items_asset_count_dict[cii] = len(campaign_item_asset_urls)
        items_assets[cii] = campaign_item_asset_urls

    ctd, created = CampaignTaskDetails.objects.get_or_create(project)
    ctd.campaign_item_count = len(collection_item_ids)
    ctd.campaign_asset_count = sum(items_asset_count_dict.values())
    ctd.save()

    ciac_details = []
    for key, value in items_asset_count_dict.items():
        ciac = CampaignItemAssetCount(
            campaign_task=ctd,
            campaign_item_identifier=key,
            campaign_item_asset_count=value,
        )
        ciac.full_clean()
        ciac_details.append(ciac)
    CampaignItemAssetCount.objects.bulk_create(ciac_details)

    for cii in collection_item_ids:
        get_save_item_assets(project, cii, items_assets[cii])


@task
def download_write_item_assets(project_id, item_url):
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

    ctd, created = CampaignTaskDetails.objects.get_or_create(project=project)
    ctd.campaign_item_count += 1
    ctd.campaign_asset_count += len(item_asset_urls)
    ctd.full_clean()
    ctd.save()

    ciac, created = CampaignItemAssetCount.objects.get_or_create(
        campaign_task=ctd, campaign_item_identifier=item_id
    )
    ciac.campaign_item_asset_count = len(item_asset_urls)
    ciac.full_clean()
    ciac.save()

    get_save_item_assets(project, item_id, item_asset_urls)

