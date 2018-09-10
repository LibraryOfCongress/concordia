import os
from collections import defaultdict
from logging import getLogger

import requests
from celery import task
from django.conf import settings
from django.template.defaultfilters import slugify

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


def get_request_data(url, params=None, timeout=120, json_resp=True, **kwargs):
    """
    :param url: give any get url
    :param params: parameters tho above url as dict
    :param timeout: connection timeout 5 sec
    :return:response dict
    """
    try:
        response = requests.get(url, params=params, timeout=timeout, **kwargs)
    except Exception as e:
        logger.error("url %s accessing error %s" % (url, str(e)))
    else:
        if response.status_code == 200:
            if not json_resp:
                return response
            return response.json()
    return {}


def get_campaign_pages(campaign_url):
    """
    Return total pages in given loc gov campaign urls
    :param campaign_url:
    :return: int total no of pages
    """
    resp = get_request_data(campaign_url, params={"fo": "json", "at": "pagination"})
    total_pages = resp.get("pagination", {}).get("total", 0)
    logger.info(
        "total_campaign_pages: %s for campaign url : %s" % (total_pages, campaign_url)
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
        resp = get_request_data(campaign_url, params={"fo": "json", "at": "results"})
        page_results = resp.get("results", [])
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
        logger.info("No item ids found for campaign url: %s" % campaign_url)

    return campaign_item_ids


def get_campaign_item_asset_urls(item_id):
    """
    :param item_id: campaign item id
    :return: item asset urls
    """
    campaign_item_asset_urls = []
    item_url = "https://www.loc.gov/item/{0}/".format(item_id)
    campaign_item_resp = get_request_data(item_url, {"fo": "json"})
    item_resources = campaign_item_resp.get("resources", [])
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


def download_write_campaign_item_asset(image_url, asset_local_path):
    """
    :param image_url:
    :param asset_local_path:
    :return:
    """
    image_response = get_request_data(image_url, stream=True, json_resp=False)

    with open(asset_local_path, "wb") as fd:
        try:
            for chunk in image_response.iter_content(chunk_size=100000):
                fd.write(chunk)
            return True
        except Exception as e:
            logger.error("Error while writing the file to disk : %s " % str(e))
    return False


def get_save_item_assets(campaign_name, project, item_id, item_asset_urls):
    """
    creates a item directory if it already does not exists, and iterates asset urls list then download each asset
    and saves to local in item directory
    :param campaign_name: campaign_name
    :param item_id: item id of the campaign
    :param item_asset_urls: list of item asset urls
    :return: nothing, it will download the assets to local path
    """

    item_local_path = os.path.join(
        settings.IMPORTER["IMAGES_FOLDER"], campaign_name, project, item_id
    )

    try:
        os.makedirs(item_local_path)
    except Exception as e:
        pass

    for idx, ciau in enumerate(item_asset_urls):
        asset_local_path = os.path.join(item_local_path, "{0}.jpg".format(str(idx)))

        download_write_campaign_item_asset(ciau, asset_local_path)


@task
def download_write_campaign_item_assets(campaign_name, project, campaign_url):
    """
    It will downloads all images from loc.gov site and saves into local directory as per campaign and items.
    :param campaign_name: campaign for requested item url
    :param campaign_url: campaign url path
    :return: nothing, will downloads the files and saves to a directory
    """
    total_pages = get_campaign_pages(campaign_url)
    campaign_item_ids = get_campaign_item_ids(campaign_url, total_pages)
    items_asset_count_dict = defaultdict(int)
    items_assets = {}

    for cii in campaign_item_ids:
        campaign_item_asset_urls = get_campaign_item_asset_urls(cii)
        items_asset_count_dict[cii] = len(campaign_item_asset_urls)
        items_assets[cii] = campaign_item_asset_urls
        # get_save_item_assets(campaign_name, project, cii, campaign_item_asset_urls)

    ctd, created = CampaignTaskDetails.objects.get_or_create(
        campaign_slug=slugify(campaign_name),
        project_slug=slugify(project),
        defaults={"campaign_name": campaign_name, "project_name": project},
    )
    ctd.campaign_item_count = len(campaign_item_ids)
    ctd.campaign_asset_count = sum(items_asset_count_dict.values())
    ctd.save()
    ciac_details = []
    for key, value in items_asset_count_dict.items():
        ciac_details.append(
            CampaignItemAssetCount(
                campaign_task=ctd,
                campaign_item_identifier=key,
                campaign_item_asset_count=value,
            )
        )
    CampaignItemAssetCount.objects.bulk_create(ciac_details)

    for cii in campaign_item_ids:
        # campaign_item_asset_urls = get_campaign_item_asset_urls(cii)
        # items_asset_count_dict[cii] = len(campaign_item_asset_urls)
        get_save_item_assets(campaign_name, project, cii, items_assets[cii])


@task
def download_write_item_assets(campaign_name, project, item_id):

    """
    It will downloads all images from loc.gov site and saves into local directory as per item level directory.
    :param campaign_name: campaign for requested item url
    :param item_url: item url path
    :return: nothing, will downloads the files and saves to a directory
    """
    item_asset_urls = get_campaign_item_asset_urls(item_id)

    ctd, created = CampaignTaskDetails.objects.get_or_create(
        campaign_slug=slugify(campaign_name),
        project_slug=slugify(project),
        defaults={"campaign_name": campaign_name, "project_name": project},
    )
    ctd.campaign_item_count += 1
    ctd.campaign_asset_count += len(item_asset_urls)
    ctd.save()
    ciac, created = CampaignItemAssetCount.objects.get_or_create(
        campaign_task=ctd, campaign_item_identifier=item_id
    )
    ciac.campaign_item_asset_count = len(item_asset_urls)
    ciac.save()

    get_save_item_assets(campaign_name, project, item_id, item_asset_urls)
