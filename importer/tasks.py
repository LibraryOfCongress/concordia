import os
from collections import defaultdict
from logging import getLogger

import requests
from celery import task
from django.conf import settings
from django.template.defaultfilters import slugify

from importer.models import CollectionItemAssetCount, CollectionTaskDetails

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


def get_collection_pages(collection_url):
    """
    Return total pages in given loc gov collection urls
    :param collection_url:
    :return: int total no of pages
    """
    resp = get_request_data(collection_url, params={"fo": "json", "at": "pagination"})
    total_pages = resp.get("pagination", {}).get("total", 0)
    logger.info(
        "total_collection_pages: %s for collection url : %s"
        % (total_pages, collection_url)
    )
    return total_pages


def get_collection_item_ids(collection_url, total_pages):
    """
    :param collection_url: collection url
    :param total_pages: number of pages in this collection url
    :return: list of collection of item ids
    """
    collection_item_ids = []
    for page_num in range(1, total_pages + 1):
        resp = get_request_data(collection_url, params={"fo": "json", "at": "results"})
        page_results = resp.get("results", [])
        for pr in page_results:
            if (
                pr.get("id")
                and pr.get("image_url")
                and "collection" not in pr.get("original_format")
                and "web page" not in pr.get("original_format")
            ):
                collection_item_url = pr.get("id")
                collection_item_ids.append(collection_item_url.split("/")[-2])
    if not collection_item_ids:
        logger.info("No item ids found for collection url: %s" % collection_url)

    return collection_item_ids


def get_collection_item_asset_urls(item_id):
    """
    :param item_id: collection item id
    :return: item asset urls
    """
    collection_item_asset_urls = []
    item_url = "https://www.loc.gov/item/{0}/".format(item_id)
    collection_item_resp = get_request_data(item_url, {"fo": "json"})
    item_resources = collection_item_resp.get("resources", [])
    for ir in item_resources:
        item_files = ir.get("files", [])
        for item_file in item_files:
            similar_img_urls = []
            for itf in item_file:
                if itf.get("mimetype") == "image/jpeg":
                    similar_img_urls.append(itf.get("url"))
            if similar_img_urls:
                collection_item_asset_urls.append(similar_img_urls[-1])

    return collection_item_asset_urls


def download_write_collection_item_asset(image_url, asset_local_path):
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


def get_save_item_assets(collection_name, project, item_id, item_asset_urls):
    """
    creates a item directory if it already does not exists, and iterates asset urls list then download each asset
    and saves to local in item directory
    :param collection_name: collection_name
    :param item_id: item id of the collection
    :param item_asset_urls: list of item asset urls
    :return: nothing, it will download the assets to local path
    """

    item_local_path = os.path.join(
        settings.IMPORTER["IMAGES_FOLDER"], collection_name, project, item_id
    )

    try:
        os.makedirs(item_local_path)
    except Exception as e:
        pass

    for idx, ciau in enumerate(item_asset_urls):
        asset_local_path = os.path.join(item_local_path, "{0}.jpg".format(str(idx)))

        download_write_collection_item_asset(ciau, asset_local_path)


@task
def download_write_collection_item_assets(collection_name, project, collection_url):
    """
    It will downloads all images from loc.gov site and saves into local directory as per collection and items.
    :param collection_name: collection for requested item url
    :param collection_url: collection url path
    :return: nothing, will downloads the files and saves to a directory
    """
    total_pages = get_collection_pages(collection_url)
    collection_item_ids = get_collection_item_ids(collection_url, total_pages)
    items_asset_count_dict = defaultdict(int)
    items_assets = {}

    for cii in collection_item_ids:
        collection_item_asset_urls = get_collection_item_asset_urls(cii)
        items_asset_count_dict[cii] = len(collection_item_asset_urls)
        items_assets[cii] = collection_item_asset_urls
        # get_save_item_assets(collection_name, project, cii, collection_item_asset_urls)

    ctd, created = CollectionTaskDetails.objects.get_or_create(
        collection_slug=slugify(collection_name),
        subcollection_slug=slugify(project),
        defaults={"collection_name": collection_name, "subcollection_name": project},
    )
    ctd.collection_item_count = len(collection_item_ids)
    ctd.collection_asset_count = sum(items_asset_count_dict.values())
    ctd.save()
    ciac_details = []
    for key, value in items_asset_count_dict.items():
        ciac_details.append(
            CollectionItemAssetCount(
                collection_task=ctd,
                collection_item_identifier=key,
                collection_item_asset_count=value,
            )
        )
    CollectionItemAssetCount.objects.bulk_create(ciac_details)

    for cii in collection_item_ids:
        # collection_item_asset_urls = get_collection_item_asset_urls(cii)
        # items_asset_count_dict[cii] = len(collection_item_asset_urls)
        get_save_item_assets(collection_name, project, cii, items_assets[cii])


@task
def download_write_item_assets(collection_name, project, item_id):

    """
    It will downloads all images from loc.gov site and saves into local directory as per item level directory.
    :param collection_name: collection for requested item url
    :param item_url: item url path
    :return: nothing, will downloads the files and saves to a directory
    """
    item_asset_urls = get_collection_item_asset_urls(item_id)

    ctd, created = CollectionTaskDetails.objects.get_or_create(
        collection_slug=slugify(collection_name),
        subcollection_slug=slugify(project),
        defaults={"collection_name": collection_name, "subcollection_name": project},
    )
    ctd.collection_item_count += 1
    ctd.collection_asset_count += len(item_asset_urls)
    ctd.save()
    ciac, created = CollectionItemAssetCount.objects.get_or_create(
        collection_task=ctd, collection_item_identifier=item_id
    )
    ciac.collection_item_asset_count = len(item_asset_urls)
    ciac.save()

    get_save_item_assets(collection_name, project, item_id, item_asset_urls)
