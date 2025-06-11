import hashlib
import os
from logging import getLogger
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse

import boto3
import requests
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
def download_asset(self, job):
    """
    Download the URL specified for an Asset and save it to working
    storage
    """
    asset = job.asset
    if hasattr(job, "url"):
        download_url = job.url
    else:
        download_url = asset.download_url
    file_extension = (
        os.path.splitext(urlparse(download_url).path)[1].lstrip(".").lower()
    )
    if not file_extension or file_extension == "jpeg":
        file_extension = "jpg"

    asset_image_filename = asset.get_asset_image_filename(file_extension)

    storage_image = download_and_store_asset_image(download_url, asset_image_filename)
    logger.info(
        "Download and storage of asset image %s complete. Setting storage_image "
        "on asset %s (%s)",
        storage_image,
        asset,
        asset.id,
    )
    asset.storage_image = storage_image
    asset.save()


def download_and_store_asset_image(download_url, asset_image_filename):
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
                f"ETag {etag} for {asset_image_filename} did not match calculated "
                f"md5 hash {filehash}"
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
            "Checksums for %s matched. Upload successful.", asset_image_filename
        )
    return asset_image_filename
