"""
See the module-level docstring for implementation details
"""

import concurrent.futures
import hashlib
import os
import re
from functools import wraps
from logging import getLogger
from tempfile import NamedTemporaryFile
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlsplit, urlunsplit

import boto3
import requests
from celery import group
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.text import slugify
from django.utils.timezone import now
from flags.state import flag_enabled
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError
from requests.packages.urllib3.util.retry import Retry

from concordia.models import Asset, Item, MediaType
from concordia.storage import ASSET_STORAGE
from importer import models

from .celery import app
from .exceptions import ImageImportFailure

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


def update_task_status(f):
    """
    Decorator which causes any function which is passed a models.TaskStatusModel
    subclass object to update on entry and exit and populate the status field
    with an exception message if raised

    Assumes that all wrapped functions get the Celery task self value as the
    first parameter and the models.TaskStatusModel subclass object as the second
    """

    @wraps(f)
    def inner(self, task_status_object, *args, **kwargs):
        # We'll do a sanity check to make sure that another process hasn't
        # updated the object status in the meantime:
        guard_qs = task_status_object.__class__._default_manager.filter(
            pk=task_status_object.pk, completed__isnull=False
        )
        if guard_qs.exists():
            logger.warning(
                "Task %s was already completed and will not be repeated",
                task_status_object,
                extra={
                    "data": {
                        "object": task_status_object,
                        "args": args,
                        "kwargs": kwargs,
                    }
                },
            )
            return

        task_status_object.last_started = now()
        task_status_object.task_id = self.request.id
        task_status_object.save()

        try:
            f(self, task_status_object, *args, **kwargs)
            task_status_object.completed = now()
            task_status_object.status = "Completed"
            task_status_object.save()
        except Exception as exc:
            task_status_object.status = "{}\n\nUnhandled exception: {}".format(
                task_status_object.status, exc
            ).strip()
            task_status_object.failed = now()
            if isinstance(exc, ImageImportFailure):
                task_status_object.failure_reason = (
                    models.TaskStatusModel.FailureReason.IMAGE
                )
            task_status_object.save()
            retry_result = task_status_object.retry_if_possible()
            if retry_result:
                task_status_object.last_started = now()
                task_status_object.task_id = retry_result.id
                task_status_object.save()
            else:
                logger.info("Retrying task %s was not possible", task_status_object)
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
        resp = requests.get(import_url, params={"fo": "json"}, timeout=30)
        resp.raise_for_status()
        item_data = resp.json()
        output = len(item_data["resources"][0]["files"])
        return f"{import_url} - Asset Count: {output}", output
    except Exception as exc:
        return f"Unhandled exception importing {import_url} {exc}", 0


def import_items_into_project_from_url(
    requesting_user, project, import_url, redownload=False
):
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

    import_job = models.ImportJob(
        project=project, created_by=requesting_user, url=import_url
    )
    import_job.full_clean()
    import_job.save()

    if url_type == "item":
        create_item_import_task.delay(import_job.pk, import_url, redownload)
    else:
        # Both collections and search results return the same format JSON
        # reponse so we can use the same code to process them:
        import_collection_task.delay(import_job.pk, redownload)

    return import_job


@app.task(bind=True)
def import_collection_task(self, import_job_pk, redownload=False):
    import_job = models.ImportJob.objects.get(pk=import_job_pk)
    return import_collection(self, import_job, redownload)


@update_task_status
def import_collection(self, import_job, redownload=False):
    item_info = get_collection_items(normalize_collection_url(import_job.url))
    for _, item_url in item_info:
        create_item_import_task.delay(import_job.pk, item_url, redownload)


@app.task(
    bind=True,
    autoretry_for=(HTTPError,),
    retry_backoff=60 * 60,
    retry_backoff_max=8 * 60 * 60,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
    rate_limit=1,
)
def redownload_image_task(self, asset_pk):
    """
    Given an existing asset object with a download_url,
    download the image and save it to asset storage, replacing
    any existing image for that asset
    """
    asset = Asset.objects.get(pk=asset_pk)
    logger.info("Redownloading %s to %s", asset.download_url, asset.get_absolute_url())
    return download_asset(self, None, asset)


@app.task(
    bind=True,
    autoretry_for=(HTTPError,),
    retry_backoff=60 * 60,
    retry_backoff_max=8 * 60 * 60,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
    rate_limit=2,
)
def create_item_import_task(self, import_job_pk, item_url, redownload=False):
    """
    Create an models.ImportItem record using the provided import job and URL by
    requesting the metadata from the URL

    Enqueues the actual import for the item once we have the metadata
    """

    import_job = models.ImportJob.objects.get(pk=import_job_pk)

    # Load the Item record with metadata from the remote URL:
    resp = requests.get(item_url, params={"fo": "json"}, timeout=30)
    resp.raise_for_status()
    item_data = resp.json()

    item, item_created = Item.objects.get_or_create(
        item_id=get_item_id_from_item_url(item_data["item"]["id"]),
        defaults={"item_url": item_url, "project": import_job.project},
    )

    import_item, import_item_created = import_job.items.get_or_create(
        url=item_url, item=item
    )

    if not item_created and redownload is False:
        # Item has already been imported and we're not redownloading
        # all items
        asset_urls, item_resource_url = get_asset_urls_from_item_resources(
            item.metadata.get("resources", [])
        )
        if item.asset_set.count() >= len(asset_urls):
            # The item has all of its assets, so we can skip it
            logger.warning("Not reprocessing existing item with all asssets: %s", item)
            import_item.status = (
                "Not reprocessing existing item with all assets: %s" % item
            )
            import_item.completed = import_item.last_started = now()
            import_item.task_id = self.request.id
            import_item.full_clean()
            import_item.save()
            return
        else:
            # The item is missing one or more of its assets, so we will reprocess it
            # to import the missing asssets
            logger.warning("Reprocessing existing item %s that is missing assets", item)

    import_item.item.metadata.update(item_data)

    populate_item_from_url(import_item.item, item_data["item"])

    item.full_clean()
    item.save()

    return import_item_task.delay(import_item.pk)


@app.task(bind=True)
def import_item_task(self, import_item_pk):
    i = models.ImportItem.objects.select_related("item").get(pk=import_item_pk)
    return import_item(self, i)


@update_task_status
def import_item(self, import_item):
    # Using transaction.atomic here ensures the data is available in the
    # database for the download_asset_task calls. If we don't do this, some
    # of the tasks could execute before the transaction is committed, causing
    # those tasks to fail since the ImportItemAsset it needs won't be in the database
    with transaction.atomic():
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
                campaign=import_item.item.project.campaign,
                title=asset_title,
                slug=slugify(asset_title, allow_unicode=True),
                sequence=idx,
                media_url=f"{idx}.jpg",
                media_type=MediaType.IMAGE,
                download_url=asset_url,
                resource_url=item_resource_url,
                storage_image="/".join([relative_asset_file_path, f"{idx}.jpg"]),
            )
            # Previously, any asset that raised a validation error was just ignored.
            # We don't want that--we want to see if an asset fails validation
            try:
                item_asset.full_clean()
            except ValidationError as exc:
                raise ValidationError(
                    f"Importing asset with slug '{item_asset.slug}' for "
                    f"item '{item_asset.item}' with resource URL "
                    f"'{item_asset.resource_url}' failed with the following "
                    f"exception: {exc}"
                ) from exc
            item_assets.append(item_asset)

        Asset.objects.bulk_create(item_assets)

        for asset in item_assets:
            import_asset = models.ImportItemAsset(
                import_item=import_item,
                asset=asset,
                url=asset.download_url,
                sequence_number=asset.sequence,
            )
            import_asset.full_clean()
            import_assets.append(import_asset)

        import_item.assets.bulk_create(import_assets)

        import_item.full_clean()
        import_item.save()

    download_asset_group = group(download_asset_task.s(i.pk) for i in import_assets)

    return download_asset_group()


# Function name is misleading since it doesn't actually take or
# use a URL, just the data retrieved from one
def populate_item_from_url(item, item_info):
    """
    Populates a Concordia.Item from the data retrieved from a loc.gov URL
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
    try:
        item_resource_url = resources[0]["url"] or ""
    except (IndexError, KeyError):
        item_resource_url = ""

    for resource in resources:
        # The JSON response for each file is a list of available image versions
        # we will attempt to save the highest resolution jpg, falling back to
        # to the highest resolution gif if there are none

        for item_file in resource.get("files", []):
            candidates = []
            backup_candidates = []

            for variant in item_file:

                if any(i for i in ("url", "height", "width") if i not in variant):
                    continue

                url = variant["url"]
                height = variant["height"]
                width = variant["width"]
                mimetype = variant.get("mimetype")

                # We prefer jpgs, but if there are none,
                # we'll fallback to gifs
                if mimetype == "image/jpeg":
                    candidates.append((url, height * width))
                elif mimetype == "image/gif":
                    backup_candidates.append((url, height * width))

            if candidates:
                candidates.sort(key=lambda i: i[1], reverse=True)
                assets.append(candidates[0][0])
            elif backup_candidates:
                backup_candidates.sort(key=lambda i: i[1], reverse=True)
                assets.append(backup_candidates[0][0])

    return assets, item_resource_url


@app.task(
    bind=True,
    autoretry_for=(HTTPError,),
    retry_backoff=60 * 60,
    retry_backoff_max=8 * 60 * 60,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
    rate_limit=1,
)
def download_asset_task(self, import_asset_pk):
    # We'll use the containing objects' slugs to construct the storage path so
    # we might as well use select_related to save extra queries:
    qs = models.ImportItemAsset.objects.select_related(
        "import_item__item__project__campaign"
    )
    try:
        import_asset = qs.get(pk=import_asset_pk)
    except models.ImportItemAsset.DoesNotExist:
        logger.exception(
            "ImportItemAsset %s could not be found while attempting to "
            "spawn download_asset task",
            import_asset_pk,
        )
        raise

    return download_asset(self, import_asset)


@update_task_status
def download_asset(self, import_asset):
    """
    Download the URL specified for an Asset and save it to working
    storage
    """
    item = import_asset.import_item.item
    download_url = import_asset.url
    asset = import_asset.asset

    asset_filename = os.path.join(
        item.project.campaign.slug,
        item.project.slug,
        item.item_id,
        "%d.jpg" % asset.sequence,
    )

    try:
        hasher = hashlib.md5(usedforsecurity=False)
        # We'll download the remote file to a temporary file
        # and after that completes successfully will upload it
        # to the defined ASSET_STORAGE.
        with NamedTemporaryFile(mode="x+b") as temp_file:
            resp = requests.get(download_url, stream=True, timeout=30)
            resp.raise_for_status()

            for chunk in resp.iter_content(chunk_size=256 * 1024):
                temp_file.write(chunk)
                hasher.update(chunk)

            # Rewind the tempfile back to the first byte so we can
            # save it to storage
            temp_file.flush()
            temp_file.seek(0)

            ASSET_STORAGE.save(asset_filename, temp_file)
    except Exception as exc:
        logger.exception("Unable to download %s to %s", download_url, asset_filename)
        raise ImageImportFailure(
            f"Unable to download {download_url} to {asset_filename}"
        ) from exc

    filehash = hasher.hexdigest()
    response = boto3.client("s3").head_object(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=asset_filename
    )
    etag = response.get("ETag")[1:-1]  # trim quotes around hash
    if filehash != etag:
        if flag_enabled("IMPORT_IMAGE_CHECKSUM"):
            logger.error(
                "ETag (%s) for %s did not match calculated md5 hash (%s) and "
                "the IMPORT_IMAGE_CHECKSUM flag is enabled",
                etag,
                asset_filename,
                filehash,
            )
            raise ImageImportFailure(
                f"ETag {etag} for {asset_filename} did not match calculated "
                f"md5 hash {filehash}"
            )
        else:
            logger.warning(
                "ETag (%s) for %s did not match calculated md5 hash (%s) but "
                "the IMPORT_IMAGE_CHECKSUM flag is disabled",
                etag,
                asset_filename,
                filehash,
            )
    else:
        logger.debug("Checksums for %s matched. Upload successful.", asset_filename)
