from __future__ import absolute_import, unicode_literals

from urllib.parse import urlparse

import requests
from celery import group, shared_task

from importer.importer.models import Importer


@shared_task
def download():
    importer = Importer()
    importer.main()


@shared_task
def check_completeness():
    importer = Importer()
    return importer.check_completeness()


@shared_task
def download_item(item_identifier):
    importer = Importer()
    importer.download_item(item_identifier)


@shared_task
def download_collection(collection_url, item_count):
    importer = Importer()
    importer.download_collection(collection_url, item_count)


@shared_task
def check_collection_completeness(collection_url, item_count):
    importer = Importer()
    return importer.check_collection_completeness(collection_url, item_count)


@shared_task
def download_async_collection(collection_url):
    get_and_save_images(collection_url)


def get_and_save_images(results_url):
    """
    Input: the url for the collection or results set
    e.g. https://www.loc.gov/collections/baseball-cards

    Page through the collection result set
    """
    params = {"fo": "json", "c": 25, "at": "results,pagination"}
    call = requests.get(results_url, params=params)
    data = call.json()
    task_signatures = []
    results = data["results"]

    for result in results:
        # Don't try to get images from the collection-level result or web page results
        if "collection" not in result.get(
            "original_format"
        ) and "web page" not in result.get("original_format"):

            # All results should have an ID and an image_url
            if result.get("image_url") and result.get("id"):
                identifier = urlparse(result["id"])[2].rstrip("/")
                identifier = identifier.split("/")[-1]
                task_signatures.append(download_item.s(identifier))

    group(task_signatures).apply_async()

    # Recurse through the next page
    if data["pagination"]["next"] is not None:
        next_url = data["pagination"]["next"]
        get_and_save_images(next_url)
