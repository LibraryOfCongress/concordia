"""
See the module-level docstring for implementation details
"""

import concurrent.futures
from logging import getLogger

from celery import chord
from PIL import Image
from requests.exceptions import HTTPError

from concordia.models import Asset
from concordia.storage import ASSET_STORAGE
from importer import models
from importer.celery import app

from .assets import download_asset
from .decorators import update_task_status
from .items import import_item_count_from_url

logger = getLogger(__name__)


def fetch_all_urls(items):
    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
        result = executor.map(import_item_count_from_url, items)
    finals = []
    totals = 0

    for value, score in result:
        totals = totals + score
        finals.append(value)

    return finals, totals


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


@app.task()
def batch_verify_asset_images_task_callback(
    results, batch, concurrency, failures_detected
):
    """
    Callback task triggered after completing a group of VerifyAssetImageJobs.

    Checks whether any verification failures occurred during the current batch
    unless a failure was previously detected. If any failure is identified,
    sets the ``failures_detected`` flag to ``True``.

    Regardless of outcome, schedules the next batch of VerifyAssetImageJobs.

    :param results: List of verification task outcomes (booleans).
    :type results: list[bool]
    :param batch: Identifier of the batch being processed.
    :type batch: UUID
    :param concurrency: Number of tasks processed concurrently per batch.
    :type concurrency: int
    :param failures_detected: Flag indicating if failures occurred previously.
    :type failures_detected: bool
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
def batch_verify_asset_images_task(self, batch, concurrency=2, failures_detected=False):
    """
    Process VerifyAssetImageJob instances for the provided batch in concurrent groups.

    Jobs are processed concurrently in groups defined by ``concurrency``. Each job
    triggers an individual verification task.

    After all VerifyAssetImageJobs for the batch have been processed:

    - If any failures occurred (``failures_detected`` is ``True``), automatically
      trigger batch processing of DownloadAssetImageJobs.
    - If no failures occurred, gracefully complete without further actions.

    :param batch: Identifier of the batch to process.
    :type batch: UUID
    :param concurrency: Number of jobs processed concurrently. Defaults to ``2``.
    :type concurrency: int, optional
    :param failures_detected: Flag indicating if failures occurred in prior job batches.
        Defaults to ``False``.
    :type failures_detected: bool, optional
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
                "Failures in VerifyAssetImageJobs in batch %s detected, so starting "
                "DownloadAssetImageJob batch",
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
def verify_asset_image_task(self, asset_pk, batch=None, create_job=False):
    """
    Verify an asset's storage image, ensuring its existence and integrity.

    Retrieves the asset by its primary key and either creates or fetches an existing
    ``VerifyAssetImageJob`` to track verification. If the asset's image fails
    verification, the job status is updated accordingly.

    This task automatically retries upon encountering ``HTTPError`` exceptions,
    applying exponential backoff.

    :param asset_pk: Primary key of the asset to verify.
    :type asset_pk: int
    :param batch: Identifier of the batch associated with this verification, if any.
        Defaults to ``None``.
    :type batch: UUID, optional
    :param create_job: If ``True``, a new ``VerifyAssetImageJob`` is created instead of
        retrieving an existing one.
    :type create_job: bool, optional

    :raises Asset.DoesNotExist: If the specified asset cannot be found.
    :raises VerifyAssetImageJob.DoesNotExist: If no existing job is found when expected.

    :return: ``True`` if verification succeeds, otherwise ``False``.
    :rtype: bool
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
                "Uncompleted VerifyAssetImageJob for asset %s and batch %s "
                "could not be found while attempting to spawn verify_asset_image task",
                asset,
                batch,
            )
            raise

    result = verify_asset_image(self, job)
    if result is True:
        job.update_status("Storage image verified")
    return result


def create_download_asset_image_job(asset, batch):
    existing_job = models.DownloadAssetImageJob.objects.filter(
        asset=asset, batch=batch
    ).first()

    if not existing_job:
        models.DownloadAssetImageJob.objects.create(asset=asset, batch=batch)


@update_task_status
def verify_asset_image(task, job):
    """
    Verify the existence and integrity of an Asset's storage image.

    Checks if the asset has a storage image set and verifies that the image
    exists in the configured storage. Then, confirms that the image file isn't
    corrupt by attempting to open and validate its contents.

    If any of these checks fail, updates the job status accordingly and creates
    a ``DownloadAssetImageJob`` to rectify the problem.

    Returns:
        bool: ``True`` if verification succeeds, ``False`` otherwise.

    Args:
        task (celery.Task): Celery task instance executing this verification.
        job (VerifyAssetImageJob): Job instance representing this verification task.
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
def batch_download_asset_images_task_callback(results, batch, concurrency):
    """
    Callback to trigger additional DownloadAssetImageJobs after a batch completes.

    This callback is automatically called after a group of DownloadAssetImageJobs
    finishes processing. Results are ignored, as they are not relevant to further
    processing. It immediately schedules the next batch of downloads, if any remain.

    :param results: Results from the completed download tasks (ignored).
    :type results: list
    :param batch: Identifier for the batch being processed.
    :type batch: UUID
    :param concurrency: Number of concurrent download tasks for the next batch.
    :type concurrency: int
    """

    # We don't care about the results of these tasks,
    # so we simply call the original task again
    batch_download_asset_images_task.delay(batch, concurrency)


@app.task(bind=True)
def batch_download_asset_images_task(self, batch, concurrency=10):
    """
    Process DownloadAssetImageJobs associated with a given batch in concurrent groups.

    Retrieves pending jobs linked to the provided ``batch`` identifier, processing them
    concurrently in groups of size defined by ``concurrency``. After each group
    finishes, recursively schedules the next group until all jobs are processed.

    :param batch: Identifier for the batch of jobs to process.
    :type batch: UUID
    :param concurrency: Number of concurrent tasks to execute per group. Defaults to
        ``10``.
    :type concurrency: int, optional
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

    # We use a chord so when the tasks finish it calls this function
    # again to start the remaining jobs until no more remain
    # Our callback just calls this task again, but we need it because
    # chords send results as the first parameter, which this task doesn't accept
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
def download_asset_image_task(self, asset_pk, batch=None, create_job=False):
    """
    Download an asset's image and create a corresponding DownloadAssetImageJob.

    Retrieves the asset by its primary key and creatres or fetches an existing
    ``DownloadAssetImageJob`` to track the download process. Then, calls the
    ``download_asset`` function to handle the actual retrieval.

    This task automatically retries upon encountering ``HTTPError`` exceptions,
    applying exponential backoff.

    :param asset_pk: Primary key of the asset to download.
    :type asset_pk: int
    :param batch: Identifier of the batch associated with this download, if any.
        Defaults to ``None``.
    :type batch: UUID, optional
    :param create_job: If ``True``, a new ``DownloadAssetImageJob`` is created instead
        of retrieving an existing one.
    :type create_job: bool, optional


    :raises Asset.DoesNotExist: If the specified asset cannot be found.
    :raises DownloadAssetImageJob.DoesNotExist: If no existing job is found
        when expected.

    :return: The result of the ``download_asset`` function, typically a status
        indicator.
    :rtype: Any
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
