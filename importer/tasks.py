"""
See the module-level docstring for implementation details
"""

import concurrent.futures
import os
import re
from functools import wraps
from logging import getLogger
from tempfile import NamedTemporaryFile
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlsplit, urlunsplit

import requests
from celery import group
from django.core.cache import cache
from django.db.transaction import atomic
from django.utils.text import slugify
from django.utils.timezone import now
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError
from requests.packages.urllib3.util.retry import Retry

from concordia.models import Asset, Item, MediaType
from concordia.storage import ASSET_STORAGE
from importer.models import ImportItem, ImportItemAsset, ImportJob

from .celery import app

logger = getLogger(__name__)

#: P1 has generic search / item pages and a number of top-level format-specific
#: “context portals” which expose the same JSON interface.
#: jq 'to_entries[] | select(.value.type == "context-portal") | .key' < manifest.json
ACCEPTED_P1_URL_PREFIXES = [
    "collections",
    "search",
    "item",
    "audio",
    "books",
    "film-and-videos",
    "manuscripts",
    "maps",
    "newspapers",
    "notated-music",
    "photos",
    "websites",
]


def requests_retry_session(
    retries=10,
    backoff_factor=5,
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


def update_task_status(f):
    """
    Decorator which causes any function which is passed a TaskStatusModel  to
    update on entry and exit and populate the status field with an exception
    message if raised

    Assumes that all wrapped functions get the Celery task self value as the
    first parameter and the TaskStatusModel subclass as the second
    """

    @wraps(f)
    def inner(self, task_status_model, *args, **kwargs):
        # We'll do a sanity check to make sure that another process hasn't
        # updated the model status in the meantime:
        guard_qs = task_status_model.__class__._default_manager.filter(
            pk=task_status_model.pk, completed__isnull=False
        )
        if guard_qs.exists():
            logger.warning(
                "Task %s was already completed and will not be repeated",
                task_status_model,
                extra={
                    "data": {
                        "object": task_status_model,
                        "args": args,
                        "kwargs": kwargs,
                    }
                },
            )
            return

        task_status_model.last_started = now()
        task_status_model.task_id = self.request.id
        task_status_model.save()

        try:
            f(self, task_status_model, *args, **kwargs)
            task_status_model.completed = now()
            task_status_model.save()
        except Exception as exc:
            task_status_model.status = "{}\n\nUnhandled exception: {}".format(
                task_status_model.status, exc
            ).strip()
            task_status_model.save()
            raise

    return inner


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
        resp = cache.get(current_page_url)
        if resp is None:
            resp = requests_retry_session().get(current_page_url)
            # 48-hour timeout
            cache.set(current_page_url, resp, timeout=(3600 * 48))

        data = resp.json()

        if "results" not in data:
            logger.error('Expected URL %s to include "results"', resp.url)
            continue

        for result in data["results"]:
            try:
                item_info = get_item_info_from_result(result)
            except Exception:
                logger.warning(
                    "Skipping result from %s which did not match expected format:",
                    resp.url,
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


def fetch_all_urls(items):
    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
        result = executor.map(import_item_count_from_url, items)
    finals = []
    totals = 0

    for value, score in result:
        totals = totals + score
        finals.append(value)

    return finals, totals


def import_item_count_from_url(import_url):
    """
    Given a loc.gov URL, return count of files from the resources section
    """
    try:
        resp = requests.get(import_url, params={"fo": "json"})
        resp.raise_for_status()
        item_data = resp.json()
        output = len(item_data["resources"][0]["files"])
        return f"{import_url} - Asset Count: {output}", output

    except Exception as exc:
        return f"Unhandled exception importing {import_url} {exc}", 0


def import_items_into_project_from_url(requesting_user, project, import_url):
    """
    Given a loc.gov URL, return the task ID for the import task
    """

    parsed_url = urlparse(import_url)

    m = re.match(
        r"^/(%s)/" % "|".join(map(re.escape, ACCEPTED_P1_URL_PREFIXES)), parsed_url.path
    )
    if not m:
        raise ValueError(
            f"{import_url} doesn't match one of the known importable patterns"
        )
    url_type = m.group(1)

    import_job = ImportJob(project=project, created_by=requesting_user, url=import_url)
    import_job.full_clean()
    import_job.save()

    if url_type == "item":
        create_item_import_task.delay(import_job.pk, import_url)
    else:
        # Both collections and search results return the same format JSON
        # reponse so we can use the same code to process them:
        import_collection_task.delay(import_job.pk)

    return import_job


@app.task(bind=True)
def import_collection_task(self, import_job_pk):
    import_job = ImportJob.objects.get(pk=import_job_pk)
    return import_collection(self, import_job)


@update_task_status
def import_collection(self, import_job):
    item_info = get_collection_items(normalize_collection_url(import_job.url))
    for _, item_url in item_info:
        create_item_import_task.delay(import_job.pk, item_url)


@app.task(
    bind=True,
    autoretry_for=(HTTPError,),
    retry_backoff=60,
    retry_backoff_max=8 * 60 * 60,
    retry_jitter=True,
    retry_kwargs={"max_retries": 12},
    rate_limit=2,
)
def redownload_image_task(self, asset_pk):
    """
    Given a tile.loc.gov URL and an existing asset object,
    download the image from tile.loc.gov and save it
    to asset storage, replacing any existing image for
    that asset
    """
    asset = Asset.objects.get(pk=asset_pk)
    logger.info("Redownloading %s to %s", asset.download_url, asset.get_absolute_url())
    return download_asset(self, None, asset)


@app.task(
    bind=True,
    autoretry_for=(HTTPError,),
    retry_backoff=60,
    retry_backoff_max=8 * 60 * 60,
    retry_jitter=True,
    retry_kwargs={"max_retries": 12},
    rate_limit=1,
)
def create_item_import_task(self, import_job_pk, item_url):
    """
    Create an ImportItem record using the provided import job and URL by
    requesting the metadata from the URL

    Enqueues the actual import for the item once we have the metadata
    """

    import_job = ImportJob.objects.get(pk=import_job_pk)

    # Load the Item record with metadata from the remote URL:
    resp = requests.get(item_url, params={"fo": "json"})
    resp.raise_for_status()
    item_data = resp.json()

    item, item_created = Item.objects.get_or_create(
        item_id=get_item_id_from_item_url(item_data["item"]["id"]),
        defaults={"item_url": item_url, "project": import_job.project},
    )

    import_item, import_item_created = import_job.items.get_or_create(
        url=item_url, item=item
    )

    if not item_created:
        logger.warning("Not reprocessing existing item %s", item)
        import_item.status = "Not reprocessing existing item %s" % item
        import_item.completed = import_item.last_started = now()
        import_item.task_id = self.request.id
        import_item.full_clean()
        import_item.save()
        return

    import_item.item.metadata.update(item_data)

    populate_item_from_url(import_item.item, item_data["item"])

    item.full_clean()
    item.save()

    return import_item_task.delay(import_item.pk)


@app.task(bind=True)
def import_item_task(self, import_item_pk):
    i = ImportItem.objects.select_related("item").get(pk=import_item_pk)
    return import_item(self, i)


@update_task_status
@atomic
def import_item(self, import_item):
    item_assets = []
    import_assets = []
    item_resource_url = None

    asset_urls, item_resource_url = get_asset_urls_from_item_resources(
        import_item.item.metadata.get("resources", [])
    )
    relative_asset_file_path = "/".join(
        [
            import_item.item.project.campaign.slug,
            import_item.item.project.slug,
            import_item.item.item_id,
        ]
    )

    for idx, asset_url in enumerate(asset_urls, start=1):
        asset_title = f"{import_item.item.item_id}-{idx}"
        item_asset = Asset(
            item=import_item.item,
            title=asset_title,
            slug=slugify(asset_title, allow_unicode=True),
            sequence=idx,
            media_url=f"{idx}.jpg",
            media_type=MediaType.IMAGE,
            download_url=asset_url,
            resource_url=item_resource_url,
            storage_image="/".join([relative_asset_file_path, f"{idx}.jpg"]),
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

    download_asset_group = group(download_asset_task.s(i.pk) for i in import_assets)

    import_item.full_clean()
    import_item.save()

    return download_asset_group()


def populate_item_from_url(item, item_info):
    """
    Populates a Concordia.Item from the provided loc.gov URL

    Returns the retrieved JSON data so additional imports can be peformed
    without a second request
    """

    for k in ("title", "description"):
        v = item_info.get(k)
        if v:
            setattr(item, k, v)

    # FIXME: this was never set before so we don't have selection logic:
    thumb_urls = [i for i in item_info["image_url"] if ".jpg" in i]
    if thumb_urls:
        item.thumbnail_url = urljoin(item.item_url, thumb_urls[0])


def get_asset_urls_from_item_resources(resources):
    """
    Given a loc.gov JSON response, return the list of asset URLs matching our
    criteria (JPEG, largest version available)
    """

    assets = []
    item_resource_url = resources[0]["url"] or ""

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

    return assets, item_resource_url


@app.task(
    bind=True,
    autoretry_for=(HTTPError,),
    retry_backoff=60,
    retry_backoff_max=8 * 60 * 60,
    retry_jitter=True,
    retry_kwargs={"max_retries": 12},
    rate_limit=2,
)
def download_asset_task(self, import_asset_pk):
    # We'll use the containing objects' slugs to construct the storage path so
    # we might as well use select_related to save extra queries:
    qs = ImportItemAsset.objects.select_related("import_item__item__project__campaign")
    import_asset = qs.get(pk=import_asset_pk)

    return download_asset(self, import_asset, None)


# FIXME: allow the redownload_images task to be run with this decorator
# present in the code. The redownload images feature will not work
# while the @update_task_status decorator is here
@update_task_status
def download_asset(self, import_asset, redownload_asset):
    """
    Download the URL specified for an Asset and save it to working
    storage
    """
    if import_asset:
        item = import_asset.import_item.item
        download_url = import_asset.url
        asset = import_asset.asset
    elif redownload_asset:
        item = redownload_asset.item
        download_url = redownload_asset.download_url
        asset = redownload_asset
    else:
        logger.exception(
            "download_asset was called without an import asset or a redownload asset"
        )
        raise

    asset_filename = os.path.join(
        item.project.campaign.slug,
        item.project.slug,
        item.item_id,
        "%d.jpg" % asset.sequence,
    )

    try:
        # We'll download the remote file to a temporary file
        # and after that completes successfully will upload it
        # to the defined ASSET_STORAGE.
        with NamedTemporaryFile(mode="x+b") as temp_file:
            resp = requests.get(download_url, stream=True)
            resp.raise_for_status()

            for chunk in resp.iter_content(chunk_size=256 * 1024):
                temp_file.write(chunk)

            # Rewind the tempfile back to the first byte so we can
            temp_file.flush()
            temp_file.seek(0)

            ASSET_STORAGE.save(asset_filename, temp_file)

    except Exception:
        logger.exception("Unable to download %s to %s", download_url, asset_filename)

        raise
