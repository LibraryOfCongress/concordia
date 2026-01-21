from logging import getLogger
from typing import Any, Optional, Sequence
from uuid import UUID

from celery import Task, chord
from PIL import Image
from requests.exceptions import HTTPError

from concordia.models import Asset
from concordia.storage import ASSET_STORAGE
from importer import models
from importer.celery import app

from .assets import download_asset
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
def redownload_image_task(self: Task, asset_pk: int) -> None:
    """
    Re-download an asset's image and persist it to storage, replacing any
    existing image.

    Looks up the Asset, creates a DownloadAssetImageJob to track work, then
    delegates to download_asset.

    Args:
        asset_pk: Primary key of the Asset to re-download.
    """
    asset = Asset.objects.get(pk=asset_pk)
    logger.info("Redownloading %s to %s", asset.download_url, asset.get_absolute_url())

    # Create a tracking job so download_asset can run under update_task_status.
    job = models.DownloadAssetImageJob.objects.create(asset=asset, batch=None)
    download_asset(self, job)


@app.task()
def batch_verify_asset_images_task_callback(
    results: Sequence[bool],
    batch: UUID,
    concurrency: int,
    failures_detected: bool,
) -> None:
    """
    Callback after a chord of VerifyAssetImageJobs completes.

    If no prior failure was noted and any result is False, mark failures as
    detected. In all cases enqueue the next verification batch.

    Args:
        results: Verification outcomes for this chord (True or False).
        batch: Identifier for the active batch.
        concurrency: Number of jobs to run in the next batch.
        failures_detected: Whether a failure was already seen.
    """
    # We only care if there are any failures, not exactly which or how many, since we
    # automatically create a DownliadImageAssetJob for each failure already, so here
    # we skip this check if we already have a detected failure
    if not failures_detected:
        # No failures so far, so we need to check the results from this latest
        # chord of tasks
        if any(result is False for result in results):
            logger.info(
                "At least one verification failure detected for batch %s", batch
            )
            failures_detected = True

    batch_verify_asset_images_task.delay(batch, concurrency, failures_detected)


@app.task(bind=True)
def batch_verify_asset_images_task(
    self: Task, batch: UUID, concurrency: int = 2, failures_detected: bool = False
) -> None:
    """
    Process VerifyAssetImageJobs in groups of size concurrency.

    After processing:
    - If any failure was detected, start a DownloadAssetImageJob batch.
    - Otherwise, end cleanly.

    Args:
        batch: Identifier for the batch to process.
        concurrency: Number of jobs to process at once. Defaults to 2.
        failures_detected: Whether earlier groups reported a failure.
            Defaults to False.
    """
    logger.info(
        "Processing next %s VerifyAssetImageJobs for batch %s", concurrency, batch
    )

    jobs_to_process = models.VerifyAssetImageJob.objects.filter(
        batch=batch, completed__isnull=True, failed__isnull=True
    ).order_by("created")

    if not jobs_to_process.exists():
        logger.info("No VerifyAssetImageJobs remain for batch %s", batch)
        if failures_detected:
            logger.info(
                "Failures in VerifyAssetImageJobs in batch %s detected, so "
                "starting DownloadAssetImageJob batch",
                batch,
            )
            batch_download_asset_images_task(batch, concurrency)
        else:
            logger.info(
                "No failures in VerifyAssetImageJob batch %s. Ending task.", batch
            )
        return

    task_group = [
        verify_asset_image_task.s(job.asset_id, batch)
        for job in jobs_to_process[:concurrency]
    ]

    chord(task_group)(
        batch_verify_asset_images_task_callback.s(batch, concurrency, failures_detected)
    )


@app.task(
    bind=True,
    autoretry_for=(HTTPError,),
    retry_backoff=60 * 60,
    retry_backoff_max=8 * 60 * 60,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
    rate_limit=1,
)
def verify_asset_image_task(
    self: Task, asset_pk: int, batch: Optional[UUID] = None, create_job: bool = False
) -> bool:
    """
    Verify that an asset's storage image exists and is readable.

    Creates or retrieves a VerifyAssetImageJob, runs verification and updates
    status. Retries on HTTPError using exponential backoff.

    Args:
        asset_pk: Primary key of the Asset to verify.
        batch: Identifier for the verification batch, if any.
        create_job: If True, create a new job; otherwise fetch an existing one.

    Returns:
        True if verification succeeds, False otherwise.

    Raises:
        Asset.DoesNotExist: When the Asset cannot be found.
        models.VerifyAssetImageJob.DoesNotExist: When fetching a job that does
            not exist.
    """
    try:
        asset = Asset.objects.get(pk=asset_pk)
    except Asset.DoesNotExist:
        logger.exception(
            "Asset %s could not be found while attempting to "
            "spawn verify_asset_image task",
            asset_pk,
        )
        raise

    if create_job:
        job = models.VerifyAssetImageJob.objects.create(asset=asset, batch=batch)
    else:
        try:
            job = models.VerifyAssetImageJob.objects.get(
                asset=asset, batch=batch, completed=None
            )
        except models.VerifyAssetImageJob.DoesNotExist:
            logger.exception(
                "Uncompleted VerifyAssetImageJob for asset %s and batch %s could not "
                "be found while attempting to spawn verify_asset_image task",
                asset,
                batch,
            )
            raise

    result = verify_asset_image(self, job)
    if result is True:
        job.update_status("Storage image verified")
    return result


def create_download_asset_image_job(asset: Asset, batch: Optional[UUID]) -> None:
    """
    Ensure a DownloadAssetImageJob exists for the given asset and batch.

    Args:
        asset: Asset to download.
        batch: Batch identifier or None.
    """
    existing_job = models.DownloadAssetImageJob.objects.filter(
        asset=asset, batch=batch
    ).first()

    if not existing_job:
        models.DownloadAssetImageJob.objects.create(asset=asset, batch=batch)


@update_task_status
def verify_asset_image(task: Task, job: Any) -> bool:
    """
    Verify the presence and integrity of an Asset's storage image.

    Checks that a storage image is set, the object exists in storage, and that
    the image bytes are not corrupt. On failure, updates job status and creates
    a DownloadAssetImageJob.

    Args:
        task: Celery task instance.
        job: VerifyAssetImageJob instance.

    Returns:
        True if verification succeeds, False otherwise.
    """
    asset = job.asset

    if not asset.storage_image or not asset.storage_image.name:
        status = f"No storage image set on {asset} ({asset.id})"
        logger.info(status)
        job.update_status(status)
        create_download_asset_image_job(asset, job.batch)
        return False
    else:
        logger.info("Storage image set on %s (%s)", asset, asset.id)

    if not ASSET_STORAGE.exists(asset.storage_image.name):
        status = f"Storage image for {asset} ({asset.id}) missing from storage"
        logger.info(status)
        job.update_status(status)
        create_download_asset_image_job(asset, job.batch)
        return False
    else:
        logger.info("Storage image for %s (%s) found in storage", asset, asset.id)

    try:
        with ASSET_STORAGE.open(asset.storage_image.name, "rb") as image_file:
            with Image.open(image_file) as image:
                image.verify()
        logger.info("Storage image for %s (%s) is not corrupt", asset, asset.id)
    except Exception as exc:
        status = (
            f"Storage image for {asset} ({asset.id}), {asset.storage_image.name}, "
            f"is corrupt. The exception raised was Type: {type(exc).__name__}, "
            f"Message: {exc}"
        )
        logger.info(status)
        job.update_status(status)
        create_download_asset_image_job(asset, job.batch)
        return False

    logger.info(
        "Storage image for %s (%s), %s, verified successfully",
        asset,
        asset.id,
        asset.storage_image.name,
    )
    return True


@app.task()
def batch_download_asset_images_task_callback(
    results: Sequence[Any], batch: UUID, concurrency: int
) -> None:
    """
    Callback after a chord of DownloadAssetImageJobs completes.

    Results are ignored. Enqueue the next download batch.

    Args:
        results: Ignored chord results.
        batch: Identifier for the batch.
        concurrency: Number of jobs to run in the next batch.
    """
    # We do not care about the results of these tasks, so we simply call the
    # original task again to continue processing the batch.
    batch_download_asset_images_task.delay(batch, concurrency)


@app.task(bind=True)
def batch_download_asset_images_task(
    self: Task, batch: UUID, concurrency: int = 10
) -> None:
    """
    Process DownloadAssetImageJobs in groups of size concurrency.

    Retrieves pending jobs for the batch, runs up to concurrency tasks, then
    schedules the next group via a chord callback until none remain.

    Args:
        batch: Identifier for the batch to process.
        concurrency: Number of concurrent tasks per group. Defaults to 10.
    """
    logger.info(
        "Processing next %s DownloadAssetImageJobs for batch %s", concurrency, batch
    )

    jobs_to_process = models.DownloadAssetImageJob.objects.filter(
        batch=batch, completed__isnull=True, failed__isnull=True
    ).order_by("created")

    if not jobs_to_process.exists():
        logger.info("No DownloadAssetImageJobs found for batch %s", batch)
        return

    task_groups = [
        download_asset_image_task.s(job.asset.pk, batch)
        for job in jobs_to_process[:concurrency]
    ]

    # Use a chord so when the tasks finish it calls the callback to start the
    # remaining jobs until no more remain. The callback just re-invokes this
    # task with the same batch and concurrency.
    chord(task_groups)(batch_download_asset_images_task_callback.s(batch, concurrency))


@app.task(
    bind=True,
    autoretry_for=(HTTPError,),
    retry_backoff=60 * 60,
    retry_backoff_max=8 * 60 * 60,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
    rate_limit=1,
)
def download_asset_image_task(
    self: Task, asset_pk: int, batch: Optional[UUID] = None, create_job: bool = False
) -> None:
    """
    Download an asset's image and track it via DownloadAssetImageJob.

    Creates or retrieves a job and delegates to download_asset. Retries on
    HTTPError using exponential backoff.

    Args:
        asset_pk: Primary key of the Asset to download.
        batch: Identifier for the batch, if any.
        create_job: If True, create a new job; otherwise fetch an existing one.

    Raises:
        Asset.DoesNotExist: When the Asset cannot be found.
        models.DownloadAssetImageJob.DoesNotExist: When fetching a job that
            does not exist.
    """
    try:
        asset = Asset.objects.get(pk=asset_pk)
    except Asset.DoesNotExist:
        logger.exception(
            "Asset %s could not be found while attempting to "
            "spawn verify_asset_image task",
            asset_pk,
        )
        raise

    if create_job:
        job = models.DownloadAssetImageJob.objects.create(asset=asset, batch=batch)
    else:
        try:
            job = models.DownloadAssetImageJob.objects.get(
                asset=asset, batch=batch, completed=None
            )
        except models.DownloadAssetImageJob.DoesNotExist:
            logger.exception(
                "Uncompleted DownloadAssetImageJob for asset %s and batch %s could not "
                "be found while attempting to spawn download_asset_image task",
                asset,
                batch,
            )
            raise

    return download_asset(self, job)
