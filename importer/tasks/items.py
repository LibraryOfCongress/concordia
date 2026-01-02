import io
import mimetypes
import os
import re
from logging import getLogger
from typing import Any, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from celery import Task, group
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.text import slugify
from django.utils.timezone import now
from PIL import Image, UnidentifiedImageError
from requests.exceptions import HTTPError

from concordia.models import Asset, Item, MediaType
from importer import models
from importer.celery import app

from .assets import download_asset_task
from .decorators import update_task_status

#: P1 has generic search / item pages and a number of top-level format-specific
#: "context portals" which expose the same JSON interface.
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

logger = getLogger(__name__)

# Tasks


@app.task(
    bind=True,
    autoretry_for=(HTTPError,),
    retry_backoff=60 * 60,
    retry_backoff_max=8 * 60 * 60,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
    rate_limit=2,
)
def create_item_import_task(
    self: Task, import_job_pk: int, item_url: str, redownload: bool = False
) -> Any:
    """
    Create an ImportItem for the given job and item URL, then enqueue its
    import.

    Fetches item metadata from the remote URL, ensures the Item and
    ImportItem exist, skips fully-imported items when not redownloading, and
    finally schedules ``import_item_task``.

    Args:
        import_job_pk: Primary key of the ImportJob.
        item_url: Absolute item URL on loc.gov.
        redownload: Reprocess an existing item even if it has all assets.

    Returns:
        The AsyncResult returned by ``import_item_task.delay``.
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
        # Item has already been imported and we are not redownloading all items.
        asset_urls, item_resource_url = get_asset_urls_from_item_resources(
            item.metadata.get("resources", [])
        )
        if item.asset_set.count() >= len(asset_urls):
            # The item has all of its assets, so we can skip it.
            logger.warning("Not reprocessing existing item with all assets: %s", item)
            import_item.update_status(
                f"Not reprocessing existing item with all assets: {item}",
                do_save=False,
            )
            import_item.completed = import_item.last_started = now()
            import_item.task_id = self.request.id
            import_item.full_clean()
            import_item.save()
            return
        else:
            # The item is missing one or more of its assets, so reprocess it.
            logger.warning("Reprocessing existing item %s that is missing assets", item)

    import_item.item.metadata.update(item_data)
    thumbnail_url = populate_item_from_data(import_item.item, item_data["item"])

    try:
        item.full_clean()
        item.save()
    except Exception as exc:
        # We create the import jobs here, so we cannot rely on the decorator to
        # update status. Update the ImportItem status manually then re-raise.
        logger.exception("Unhandled exception when importing item %s", item)
        new_status = "{}\n\nUnhandled exception: {}".format(
            import_item.status, exc
        ).strip()
        import_item.update_status(new_status, do_save=False)
        import_item.failed = now()
        import_item.task_id = self.request.id
        import_item.save()
        raise

    download_and_set_item_thumbnail(item, thumbnail_url)

    return import_item_task.delay(import_item.pk)


@app.task(bind=True)
def import_item_task(self: Task, import_item_pk: int) -> Any:
    """
    Enqueue downloads for all assets of a previously created ImportItem.

    Args:
        import_item_pk: Primary key of the ImportItem to process.

    Returns:
        The result of the celery group that downloads assets.
    """
    i = models.ImportItem.objects.select_related("item").get(pk=import_item_pk)
    return import_item(self, i)


@update_task_status
def import_item(self: Task, import_item: Any) -> Any:
    """
    Create Asset rows for an ImportItem, create ImportItemAsset rows, then
    enqueue downloads for all assets.

    Wrapped with ``update_task_status`` to keep job fields updated.

    Args:
        self: Celery Task instance.
        import_item: ImportItem instance being processed.

    Returns:
        A celery group result for the scheduled download tasks.
    """
    # Using transaction.atomic here ensures the data is available in the
    # database for the download_asset_task calls. If we do not do this some
    # tasks could execute before the transaction is committed, causing failures.
    with transaction.atomic():
        item_assets: List[Asset] = []
        import_assets: List[Any] = []
        item_resource_url: Optional[str] = None

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

        for sequence, asset_url in enumerate(asset_urls, start=1):
            asset_title = f"{import_item.item.item_id}-{sequence}"
            file_extension = (
                os.path.splitext(urlparse(asset_url).path)[1].lstrip(".").lower()
            )
            item_asset = Asset(
                item=import_item.item,
                campaign=import_item.item.project.campaign,
                title=asset_title,
                slug=slugify(asset_title, allow_unicode=True),
                sequence=sequence,
                media_type=MediaType.IMAGE,
                download_url=asset_url,
                resource_url=item_resource_url,
                storage_image="/".join(
                    [relative_asset_file_path, f"{sequence}.{file_extension}"]
                ),
            )
            # Previously any asset that raised a validation error was ignored.
            # We want validation errors to fail the import.
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


# End tasks


def import_item_count_from_url(import_url: str) -> Tuple[str, int]:
    """
    Return a tuple of status string and asset count for a loc.gov item URL.

    Args:
        import_url: Absolute item URL.

    Returns:
        A pair of ``(status_message, count)``. On error returns a message and
        count 0.
    """
    try:
        resp = requests.get(import_url, params={"fo": "json"}, timeout=30)
        resp.raise_for_status()
        item_data = resp.json()
        output = len(item_data["resources"][0]["files"])
        return f"{import_url} - Asset Count: {output}", output
    except Exception as exc:
        return f"Unhandled exception importing {import_url} {exc}", 0


def get_item_info_from_result(
    result: dict,
) -> Optional[Tuple[str, str]]:
    """
    Extract an item_id and item_url from a P1 search result.

    Skips results with unsupported formats or without an image_url.

    Args:
        result: A single result object from the P1 JSON response.

    Returns:
        ``(item_id, item_url)`` when supported, otherwise None.
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
        return None

    image_url = result.get("image_url")
    if not image_url:
        logger.info(
            "Skipping result %s because it lacks an image_url",
            item_id,
            extra={"data": {"result": result}},
        )
        return None

    item_url = result["url"]

    m = re.search(r"loc.gov/item/([^/]+)", item_url)
    if not m:
        logger.info(
            "Skipping %s because the URL %s doesn't appear to be an item!",
            item_id,
            item_url,
            extra={"data": {"result": result}},
        )
        return None

    return m.group(1), item_url


def get_item_id_from_item_url(item_url: str) -> str:
    """
    Extract the item_id component from a loc.gov item URL.

    Args:
        item_url: Absolute item URL.

    Returns:
        The item_id string.
    """
    if item_url.endswith("/"):
        item_id = item_url.split("/")[-2]
    else:
        item_id = item_url.split("/")[-1]
    return item_id


def import_items_into_project_from_url(
    requesting_user: Any, project: Any, import_url: str, redownload: bool = False
) -> Any:
    """
    Create an ImportJob for the given URL and enqueue item or collection import.

    Determines whether the URL is an item or a collection/search URL and
    schedules the appropriate task.

    Args:
        requesting_user: User creating the ImportJob.
        project: Project that will own the imported Items.
        import_url: loc.gov item or collection/search URL.
        redownload: Reprocess existing items even if they have all assets.

    Returns:
        The created ImportJob instance.
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
        # response so we can use the same code to process them.
        from .collections import import_collection_task

        import_collection_task.delay(import_job.pk, redownload)

    return import_job


def populate_item_from_data(item: Item, item_info: dict) -> Optional[str]:
    """
    Populate an Item from a loc.gov item JSON fragment.

    Sets title and description when present. Chooses a JPG thumbnail URL if
    available, stores it on the Item, and returns the resolved URL.

    Args:
        item: The Item instance to update.
        item_info: The ``item`` object from the P1 response.

    Returns:
        The resolved thumbnail URL when found, otherwise None.
    """
    for k in ("title", "description"):
        v = item_info.get(k)
        if v:
            setattr(item, k, v)

    # FIXME: this was never set before so we do not have selection logic.
    thumb_urls = [i for i in item_info["image_url"] if ".jpg" in i]
    if thumb_urls:
        item.thumbnail_url = urljoin(item.item_url, thumb_urls[0])
    try:
        image_urls = item_info.get("image_url") or []
        thumb_urls = [u for u in image_urls if ".jpg" in u]
    except Exception:
        thumb_urls = []

    if thumb_urls:
        resolved = urljoin(item.item_url, thumb_urls[0])
        # TODO: remove setting thumbnail_url once field is removed.
        item.thumbnail_url = resolved
        return resolved
    return None


def get_asset_urls_from_item_resources(
    resources: List[dict],
) -> Tuple[List[str], str]:
    """
    From a P1 resources list, pick best image URL per file.

    Prefers the largest JPEG variant per file. If no JPEGs exist, falls back
    to the largest GIF. Also returns the item resource URL when available.

    Args:
        resources: The ``resources`` array from the P1 response.

    Returns:
        A tuple of ``(asset_urls, item_resource_url)``.
    """
    assets: List[str] = []
    try:
        item_resource_url = resources[0]["url"] or ""
    except (IndexError, KeyError):
        item_resource_url = ""

    for resource in resources:
        # Each "file" contains a set of variants. Select the largest preferred
        # type per file.
        for item_file in resource.get("files", []):
            candidates: List[Tuple[str, int]] = []
            backup_candidates: List[Tuple[str, int]] = []

            for variant in item_file:
                if any(i for i in ("url", "height", "width") if i not in variant):
                    continue

                url = variant["url"]
                height = variant["height"]
                width = variant["width"]
                mimetype = variant.get("mimetype")

                # Prefer JPEG; if none exist use GIF.
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


def _guess_extension(content_type: Optional[str], url_path: str) -> str:
    """Guess a safe extension from Content-Type or URL, defaulting to .bin."""
    if content_type:
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if ext:
            return ext
    _, ext = os.path.splitext(url_path)
    if ext:
        return ext.lower()
    return ".bin"


def _safe_filename(item: Item, ext: str) -> str:
    """Build a filename for the item's thumbnail."""
    base = slugify(item.item_id or f"item-{item.pk}") or f"item-{item.pk}"
    return f"{base}{ext}"


def download_and_set_item_thumbnail(
    item: Item,
    url: str,
    force: bool = False,
    connect_timeout: float = 5.0,
    read_timeout: float = 30.0,
) -> str:
    """
    Download an image from url and save it to item.thumbnail_image.

    The image is validated with Pillow. The function will not set a new
    thumbnail_image if one already exists unless ``force=True``. Filename is
    stable per item and inferred from Content-Type or URL with a safe fallback.

    Args:
        item: The Item instance to modify and save.
        url: Absolute URL for the image to download.
        force: Overwrite an existing thumbnail if True.
        connect_timeout: Requests connect timeout in seconds.
        read_timeout: Requests read timeout in seconds.

    Returns:
        The storage path of the saved image, or a message if skipped.

    Raises:
        ValueError: If the image is invalid.
        requests.RequestException: Network errors during download.
    """
    # Lock the row briefly to avoid pointless work if someone else is writing.
    with transaction.atomic():
        locked = (
            Item.objects.select_for_update(of=("self",))
            .only("id", "thumbnail_image")
            .get(pk=item.pk)
        )
        if locked.thumbnail_image and not force:
            msg = "Thumbnail already exists; skipping (use force=True to overwrite)."
            logger.warning(
                "download_and_set_item_thumbnail: %s item_pk=%s", msg, item.pk
            )
            return msg

    timeout = (connect_timeout, read_timeout)
    logger.info(
        "download_and_set_item_thumbnail: downloading url=%s item_pk=%s",
        url,
        item.pk,
    )

    with requests.get(url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        content_type = (resp.headers.get("Content-Type") or "").lower()

        buf = io.BytesIO()
        for chunk in resp.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            buf.write(chunk)

    # Validate image integrity with Pillow.
    try:
        buf.seek(0)
        with Image.open(buf) as img:
            img.verify()
    except UnidentifiedImageError as exc:
        raise ValueError("Downloaded file is not a valid image.") from exc

    # Decide file extension. Try header, URL, then Pillow.
    url_path = urlparse(url).path
    ext = _guess_extension(content_type, url_path)
    # If we got a blank or .bin extension we could not infer it from headers
    # or URL. Inspect bytes with Pillow, default to jpg.
    if ext in (".bin", ""):
        try:
            buf.seek(0)
            with Image.open(buf) as probe:
                fmt = (probe.format or "").lower()
            ext = {
                "jpeg": ".jpg",
                "jpg": ".jpg",
                "png": ".png",
                "gif": ".gif",
                "webp": ".webp",
                "tiff": ".tif",
                "bmp": ".bmp",
            }.get(fmt, ".jpg")
        finally:
            buf.seek(0)

    filename = _safe_filename(item, ext)
    content = ContentFile(buf.getvalue())

    with transaction.atomic():
        locked = Item.objects.select_for_update(of=("self",)).get(pk=item.pk)
        if locked.thumbnail_image and not force:
            msg = (
                "Thumbnail already present after download; skipping save. "
                "Use force=True to overwrite."
            )
            logger.warning(
                "download_and_set_item_thumbnail: %s item_id=%s", msg, item.pk
            )
            return msg
        locked.thumbnail_image.save(filename, content, save=True)
        logger.info(
            "download_and_set_item_thumbnail: saved as %s item_id=%s",
            locked.thumbnail_image.name,
            locked.pk,
        )
    return locked.thumbnail_image.name
