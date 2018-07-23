import os
from logging import getLogger

import requests
from celery import task
from django.conf import settings
from rest_framework.response import Response

from importer.models import CollectionItemAssetCount, CollectionTaskDetails

logger = getLogger(__name__)


def get_request_data(url, params=None, retry_count=1):
    response = requests.get(url, params=params)
    if response.status_code != 200:
        return get_request_data(url, params, retry_count + 1)
    return response.json()


def get_collection_pages(collection_url):
    collection_url, collection_params = get_collection_params(collection_url)
    params = dict(list(collection_params.items()) + list({"fo": "json"}.items()))
    resp = get_request_data(collection_url, params)
    total_collection_pages = resp.get("pagination", {}).get("total", 0)
    logger.info(
        "total_collection_pages: %s for collection url : %s"
        % (total_collection_pages, collection_url)
    )
    return total_collection_pages


def get_collection_params(collection_url):
    if "?fa" in collection_url:
        collection_url_splits = collection_url.split("?fa=")
        collection_url = collection_url_splits[0]
        collection_params = {"fa": collection_url_splits[1]}
        return collection_url, collection_params
    else:
        return collection_url, {}


def get_collection_item_ids(collection_name, collection_url):
    collection_item_ids = []
    total_pages_count = get_collection_pages(collection_url)
    for page_num in range(1, total_pages_count + 1):
        resp = get_request_data(collection_url + "&fo=json")
        page_results = resp.get("results", [])
        print("page results: ", page_results)
        if page_results:
            for pr in page_results:
                if (
                    pr.get("id")
                    and pr.get("image_url")
                    and "collection" not in pr.get("original_format")
                    and "web page" not in pr.get("original_format")
                ):
                    collection_item_url = pr.get("id")
                    collection_item_ids.append(collection_item_url.split("/")[-2])
        else:
            return Response(
                {
                    "message": 'No page results found for collection : "%s" from loc API'
                    % collection_url
                }
            )

    try:
        ctd = CollectionTaskDetails.objects.get(collection_slug=collection_name)
        ctd.collection_page_count = total_pages_count
        ctd.collection_item_count = len(collection_item_ids)
        ctd.save()
    except Exception as e:
        logger.error(
            "error while creating entries into Collection Task Details models: %s " % e
        )
        return Response(
            {
                "message": "Unable to create item entries for collection : %s"
                % collection_name
            }
        )
    print("collection_item_ids: ", collection_item_ids)
    return collection_item_ids


def get_collection_item_asset_urls(collection_name, item_id):
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
            collection_item_asset_urls.append(similar_img_urls[-1])

    try:
        ctd = CollectionTaskDetails.objects.get(collection_slug=collection_name)

        ctd.collection_asset_count = ctd.collection_asset_count + len(
            collection_item_asset_urls
        )
        ctd.save()

        ciac_details = {
            "collection_slug": ctd.collection_slug,
            "collection_item_identifier": item_id,
            "collection_item_asset_count": len(collection_item_asset_urls),
        }
        ciac = CollectionItemAssetCount.objects.create(**ciac_details)
        ciac.save()
    except CollectionTaskDetails.DoesNotExist as e:
        logger.error(
            "error while creating entries into Collection Task Details models: %s " % e
        )
    except Exception as e1:
        logger.error(
            "error while creating entries into CollectionItemAssetCount models: %s "
            % e1
        )

    return collection_item_asset_urls


def download_write_collection_item_asset(image_url, asset_local_path, retry_count=1):
    image_response = requests.get(image_url, stream=True)

    with open(asset_local_path, "wb") as fd:
        try:
            for chunk in image_response.iter_content(chunk_size=100000):
                fd.write(chunk)
            return True
        except Exception as e:
            logger.error("Error while writing the file to disk : %s " % e)
            if retry_count >= 3:
                return False
            download_write_collection_item_assets(
                image_url, asset_local_path, retry_count=retry_count + 1
            )


@task
def download_write_collection_item_assets(collection_name, collection_url):
    """
    It will downloads all images from loc.gov site and saves into local directory as per collection and items.
    :param collection_name: collection for requested item url
    :param collection_url: collection url path
    :return: nothing, will downloads the files and saves to a directory
    """
    collection_item_ids = get_collection_item_ids(collection_name, collection_url)
    for cii in collection_item_ids:
        print("getting item id and assets list: ", cii)
        collection_item_asset_urls = get_collection_item_asset_urls(
            collection_name, cii
        )
        get_save_item_assets(collection_name, cii, collection_item_asset_urls)


@task
def download_write_item_assets(collection_name, item_url):
    """
    It will downloads all images from loc.gov site and saves into local directory as per item level directory.
    :param collection_name: collection for requested item url
    :param item_url: item url path
    :return: nothing, will downloads the files and saves to a directory
    """
    item_asset_urls = []
    item_response = get_request_data(item_url, {"fo": "json"})
    item_id = get_item_id_from_item_url(item_url)
    item_resources = item_response.get("resources", [])
    for ir in item_resources:
        item_files = ir.get("files", [])
        print("item_files: ", item_files, type(item_files), len(item_files))
        for item_file in item_files:
            print("item_file: ", item_file)
            similar_img_urls = []
            for itf in item_file:
                print("itf:", itf, type(itf))
                if itf.get("mimetype") == "image/jpeg":
                    similar_img_urls.append(itf.get("url"))
            item_asset_urls.append(similar_img_urls[-1])

    try:
        ctd = CollectionTaskDetails.objects.get(collection_slug=collection_name)
        ciac_details = {
            "collection_slug": ctd.collection_slug,
            "collection_item_identifier": item_id,
            "collection_item_asset_count": len(item_asset_urls),
        }
        ciac = CollectionItemAssetCount.objects.create(**ciac_details)
        ciac.save()
    except CollectionTaskDetails.DoesNotExist as e:
        logger.error(
            "error while creating entries into Collection Task Details models: %s " % e
        )
    except Exception as e1:
        logger.error(
            "error while creating entries into CollectionItemAssetCount models: %s "
            % e1
        )

    get_save_item_assets(collection_name, item_id, item_asset_urls)


def get_save_item_assets(collection_name, item_id, item_asset_urls):
    """
    creates a item directory if it already does not exists, and iterates asset urls list then download each asset
    and saves to local in item directory
    :param collection_name: collection_name
    :param item_id: item id of the collection
    :param item_asset_urls: list of item asset urls
    :return: nothing, it will download the assets to local path
    """

    item_local_path = os.path.join(
        settings.IMPORTER["IMAGES_FOLDER"], collection_name, item_id
    )

    try:
        os.makedirs(item_local_path)
    except Exception as e:
        pass

    for idx, ciau in enumerate(item_asset_urls):
        asset_local_path = os.path.join(item_local_path, "{0}.jpg".format(str(idx)))

        download_write_collection_item_asset(ciau, asset_local_path)


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
