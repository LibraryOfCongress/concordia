from logging import getLogger
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from django.core.cache import cache
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from importer import models
from importer.celery import app

from .decorators import update_task_status
from .items import create_item_import_task, get_item_info_from_result

logger = getLogger(__name__)

# Tasks


@app.task(bind=True)
def import_collection_task(self, import_job_pk, redownload=False):
    import_job = models.ImportJob.objects.get(pk=import_job_pk)
    return import_collection(self, import_job, redownload)


@update_task_status
def import_collection(self, import_job, redownload=False):
    item_info = get_collection_items(normalize_collection_url(import_job.url))
    for _, item_url in item_info:
        create_item_import_task.delay(import_job.pk, item_url, redownload)


# End tasks


def requests_retry_session(
    retries=3,
    backoff_factor=60 * 60,
    status_forcelist=(429, 500, 502, 503, 504),
    session=None,
):
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


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
        resp = cache.get(current_page_url)
        if resp is None:
            resp = requests_retry_session().get(current_page_url)
            # 48-hour timeout
            cache.set(current_page_url, resp, timeout=(3600 * 48))

        data = resp.json()

        results = data.get("results", None)
        if results:
            for result in results:
                try:
                    item_info = get_item_info_from_result(result)
                    if item_info:
                        items.append(item_info)
                except Exception:
                    logger.warning(
                        "Skipping result from %s which did not match expected format:",
                        current_page_url,
                        exc_info=True,
                        extra={"data": {"result": result, "url": current_page_url}},
                    )
        else:
            logger.error('Expected URL %s to include "results"', current_page_url)

        current_page_url = data.get("pagination", {}).get("next", None)

    if not items:
        logger.warning("No valid items found for collection url: %s", collection_url)

    return items
