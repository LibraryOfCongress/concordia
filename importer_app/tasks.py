
import requests
from logging import getLogger
from celery import shared_task, task
import os
from django.conf import settings
from importer_app.models import CollectionTaskDetails, CollectionItemAssetCount


logger = getLogger(__name__)

def get_request_data(url, params=None):
    response = requests.get(url, params=params)
    if response.status_code != 200:
        return False
    return response.json()


def get_collection_pages(collection_url):
    resp = get_request_data(collection_url, {"fo": "json", "at": "pagination"})
    total_collection_pages = resp.get('pagination', {}).get('total', 0)
    return total_collection_pages


def get_collection_item_ids(collection_name, collection_url):
    collection_item_ids = []
    total_pages_count = get_collection_pages(collection_url)
    for page_num in range(1, total_pages_count + 1):
        resp = get_request_data(collection_url, {"fo": "json", "sp": page_num, "at": "results"})
        page_results = resp.get('results')
        for pr in page_results:
            if pr.get('id') and pr.get('image_url') and "collection" not in pr.get(
                "original_format") and "web page" not in pr.get("original_format"):
                collection_item_url = pr.get('id')
                collection_item_ids.append(collection_item_url.split("/")[-2])

    try:
        ctd = CollectionTaskDetails.objects.get(collection_slug=collection_name)
        ctd.collection_page_count = total_pages_count
        ctd.collection_item_count = len(collection_item_ids)
        ctd.save()
    except Exception as e:
        logger.error("error while creating entries into Collection Task Details models: %s " % e)
    return collection_item_ids


def get_collection_item_asset_urls(collection_name, item_id):
    collection_item_asset_urls = []
    item_url = 'https://www.loc.gov/item/{0}/'.format(item_id)
    collection_item_resp = get_request_data(item_url, {"fo": "json"})
    item_resources = collection_item_resp.get('resources', [])
    for ir in item_resources:
        item_files = ir.get('files', [])[0]
        for item_file in item_files:
            if item_file.get('mimetype') == 'image/jpeg':
                collection_item_asset_urls.append(item_file.get('url'))

    try:
        ctd = CollectionTaskDetails.objects.get(collection_slug=collection_name)

        ctd.collection_asset_count = ctd.collection_asset_count + len(collection_item_asset_urls)
        ctd.save()

        ciac_details = {'collection_slug': ctd.collection_slug,
                        'collection_item_identifier': item_id,
                        'collection_item_asset_count': len(collection_item_asset_urls)}
        ciac = CollectionItemAssetCount.objects.create(**ciac_details)
        ciac.save()
    except CollectionTaskDetails.DoesNotExist as e:
        logger.error("error while creating entries into Collection Task Details models: %s " % e)
    except Exception as e1:
        logger.error("error while creating entries into CollectionItemAssetCount models: %s " % e1)

    return collection_item_asset_urls


def download_write_collection_item_asset(image_url, asset_local_path, retry_count=1):
    image_response = requests.get(image_url, stream=True)

    with open(asset_local_path, "wb") as fd:
        try:
            for chunk in image_response.iter_content(chunk_size=100000):
                fd.write(chunk)
            return True
        except Exception as e:
            print(e)
            if retry_count >= 3:
                return False
            download_write_collection_item_assets(image_url, asset_local_path, retry_count=retry_count+1)


@task
def download_write_collection_item_assets(collection_name, collection_url):
    collection_item_ids = get_collection_item_ids(collection_name, collection_url)
    for cii in collection_item_ids:
        collection_item_asset_urls = get_collection_item_asset_urls(collection_name, cii)
        item_local_path = os.path.join(settings.IMPORTER['IMAGES_FOLDER'], collection_name, cii)

        try:
            os.makedirs(item_local_path)
        except Exception as e:
            print(e)

        for idx, ciau in enumerate(collection_item_asset_urls):

            asset_local_path = os.path.join(item_local_path, '{0}.jpg'.format(str(idx)))

            download_write_collection_item_asset(ciau, asset_local_path)
