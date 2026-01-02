from logging import getLogger
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from celery import Task
from django.core.cache import cache
from requests import Session
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from importer import models
from importer.celery import app

from .decorators import update_task_status
from .items import create_item_import_task, get_item_info_from_result

logger = getLogger(__name__)

# Tasks


@app.task(bind=True)
def import_collection_task(
    self: Task, import_job_pk: int, redownload: bool = False
) -> None:
    """
    Celery entrypoint to import all items from a P1 collection or search URL.

    Looks up the ``ImportJob`` and delegates to ``import_collection``.

    Args:
        import_job_pk: Primary key of the ImportJob.
        redownload: If true, force re-download of assets when creating tasks.
    """
    import_job = models.ImportJob.objects.get(pk=import_job_pk)
    import_collection(self, import_job, redownload)


@update_task_status
def import_collection(
    self: Task, import_job: models.ImportJob, redownload: bool = False
) -> None:
    """
    Enqueue item import tasks for every item in a normalized collection URL.

    Args:
        import_job: The ImportJob that initiated the collection import.
        redownload: If true, force re-download of assets.
    """
    item_info = get_collection_items(normalize_collection_url(import_job.url))
    for _, item_url in item_info:
        create_item_import_task.delay(import_job.pk, item_url, redownload)


# End tasks


def requests_retry_session(
    retries: int = 3,
    backoff_factor: float = 60 * 60,
    status_forcelist: tuple[int, ...] = (429, 500, 502, 503, 504),
    session: Optional[Session] = None,
) -> Session:
    """
    Build a ``requests.Session`` with retry behavior for transient failures.

    Args:
        retries: Total number of retry attempts.
        backoff_factor: Multiplier for exponential backoff in seconds.
        status_forcelist: HTTP status codes that trigger a retry.
        session: Optional existing session to configure.

    Returns:
        A ``requests.Session`` with retry adapters mounted.
    """
    sess = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    sess.mount("http://", adapter)
    sess.mount("https://", adapter)
    return sess


def normalize_collection_url(original_url: str) -> str:
    """
    Normalize a P1 collection or search URL for import.

    Rewrites query params needed for JSON output and pagination. Leaves other
    filters intact.

    Args:
        original_url: The source collection or search URL.

    Returns:
        A normalized URL with ``fo=json`` and without conflicting params.
    """
    parsed_url = urlsplit(original_url)

    new_qs = [("fo", "json")]

    for k, v in parse_qsl(parsed_url.query):
        if k not in ("fo", "at", "sp"):
            new_qs.append((k, v))

    return urlunsplit(
        (parsed_url.scheme, parsed_url.netloc, parsed_url.path, urlencode(new_qs), None)
    )


def get_collection_items(collection_url: str) -> list[tuple[str, str]]:
    """
    Walk a P1 collection or search endpoint and collect item IDs and URLs.

    Caches each page response for 48 hours to reduce repeated network calls.

    Args:
        collection_url: URL of a loc.gov collection or search results page.

    Returns:
        A list of ``(item_id, item_url)`` tuples discovered across pages.
    """
    items: list[tuple[str, str]] = []
    current_page_url: Optional[str] = collection_url

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
