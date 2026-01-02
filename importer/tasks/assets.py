import hashlib
import os
from logging import getLogger
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse

import boto3
import requests
from celery import Task
from django.conf import settings
from flags.state import flag_enabled
from requests.exceptions import HTTPError

from concordia.storage import ASSET_STORAGE
from importer import models
from importer.celery import app
from importer.exceptions import ImageImportFailure

from .decorators import update_task_status

logger = getLogger(__name__)


@app.task(
    bind=True,
    autoretry_for=(HTTPError,),
    retry_backoff=60 * 60,
    retry_backoff_max=8 * 60 * 60,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
    rate_limit=1,
)
def download_asset_task(self: Task, import_asset_pk: int) -> None:
    """
    Download and persist an asset image for the given ImportItemAsset.

    Looks up the ImportItemAsset with related objects to reduce queries, then
    delegates to ``download_asset``. Retries on ``HTTPError`` per task config.

    Args:
        import_asset_pk: Primary key of the ImportItemAsset to process.

    Raises:
        models.ImportItemAsset.DoesNotExist: If the job row does not exist.
        ImageImportFailure: If the download or verification fails.
    """
    # Use select_related since slugs from the container objects form the path.
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

    download_asset(self, import_asset)


@update_task_status
def download_asset(self: Task, job: "models.ImportItemAsset") -> None:
    """
    Download the image for the given job and save it to working storage.

    The URL is taken from ``job.url`` when present, otherwise from
    ``job.asset.download_url``. The extension is inferred from the URL path
    and normalized so ``jpeg`` becomes ``jpg``. On success the asset's
    ``storage_image`` field is updated.

    Args:
        job: ImportItemAsset containing the target asset and optional URL.

    Raises:
        ImageImportFailure: If the download, upload or checksum check fails.
    """
    asset = job.asset
    download_url: str = job.url if hasattr(job, "url") else asset.download_url

    file_extension = (
        os.path.splitext(urlparse(download_url).path)[1].lstrip(".").lower()
    )
    if not file_extension or file_extension == "jpeg":
        file_extension = "jpg"

    asset_image_filename = asset.get_asset_image_filename(file_extension)

    storage_image = download_and_store_asset_image(download_url, asset_image_filename)
    logger.info(
        "Download and storage of asset image %s complete. Setting "
        "storage_image on asset %s (%s)",
        storage_image,
        asset,
        asset.id,
    )
    asset.storage_image = storage_image
    asset.save()


def download_and_store_asset_image(download_url: str, asset_image_filename: str) -> str:
    """
    Stream a remote image to a temp file, upload it to storage, then verify.

    The file is streamed and hashed with MD5, uploaded to ``ASSET_STORAGE``,
    then the object metadata is fetched via S3 ``head_object`` and the ETag is
    compared to the computed MD5. When the ``IMPORT_IMAGE_CHECKSUM`` flag is
    enabled a mismatch raises ``ImageImportFailure``. When disabled a warning
    is logged.

    Args:
        download_url: HTTP(S) URL of the image to fetch.
        asset_image_filename: Destination key or path in storage.

    Returns:
        The storage key that was written.

    Raises:
        ImageImportFailure: On HTTP errors, I/O errors or checksum mismatch.
    """
    try:
        hasher = hashlib.md5(usedforsecurity=False)
        # Download the remote file to a temp file then upload to storage.
        with NamedTemporaryFile(mode="x+b") as temp_file:
            resp = requests.get(download_url, stream=True, timeout=30)
            resp.raise_for_status()

            for chunk in resp.iter_content(chunk_size=256 * 1024):
                temp_file.write(chunk)
                hasher.update(chunk)

            temp_file.flush()
            temp_file.seek(0)
            ASSET_STORAGE.save(asset_image_filename, temp_file)
    except Exception as exc:
        logger.exception(
            "Unable to download %s to %s", download_url, asset_image_filename
        )
        raise ImageImportFailure(
            f"Unable to download {download_url} to {asset_image_filename}"
        ) from exc

    filehash = hasher.hexdigest()
    response = boto3.client("s3").head_object(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=asset_image_filename
    )
    etag = response.get("ETag")[1:-1]  # trim quotes around hash

    if filehash != etag:
        if flag_enabled("IMPORT_IMAGE_CHECKSUM"):
            logger.error(
                "ETag (%s) for %s did not match calculated md5 hash (%s) and "
                "the IMPORT_IMAGE_CHECKSUM flag is enabled",
                etag,
                asset_image_filename,
                filehash,
            )
            raise ImageImportFailure(
                f"ETag {etag} for {asset_image_filename} did not match "
                f"calculated md5 hash {filehash}"
            )
        else:
            logger.warning(
                "ETag (%s) for %s did not match calculated md5 hash (%s) but "
                "the IMPORT_IMAGE_CHECKSUM flag is disabled",
                etag,
                asset_image_filename,
                filehash,
            )
    else:
        logger.info(
            "Checksums for %s matched. Upload successful.",
            asset_image_filename,
        )

    return asset_image_filename
