from collections.abc import Iterable
from itertools import islice
from uuid import UUID

from importer.models import VerifyAssetImageJob
from importer.tasks.images import batch_verify_asset_images_task

BATCH_SIZE: int = 100


def create_verify_asset_image_job_batch(
    asset_pks: Iterable[int],
    batch: UUID,
) -> tuple[int, str]:
    """
    Create verification jobs in chunks and enqueue a single batch task.

    Iterates through the provided asset primary keys in chunks of
    `BATCH_SIZE`, creating `VerifyAssetImageJob` rows via `bulk_create`.
    After all jobs are created, schedules the Celery task that verifies
    the images for the given batch. Returns the number of jobs created
    and the admin URL prefiltered to the batch.

    Args:
        asset_pks (Iterable[int]): Asset primary keys to generate jobs for.
        batch (UUID): Identifier to group jobs; unrelated to chunk size.

    Returns:
        tuple[int, str]: A pair of `(job_count, batch_admin_url)`.
    """

    job_count = 0
    # Make sure asset_pks is an iterator, for proper use with islice
    # Not doing this causes an infinite loop if asset_pks is not an iterator/generator
    asset_pks = iter(asset_pks)
    while True:
        asset_batch = list(islice(asset_pks, BATCH_SIZE))
        if not asset_batch:
            break
        job_count += len(
            VerifyAssetImageJob.objects.bulk_create(
                [
                    VerifyAssetImageJob(asset_id=asset_pk, batch=batch)
                    for asset_pk in asset_batch
                ],
                batch_size=BATCH_SIZE,
            )
        )

    batch_verify_asset_images_task.delay(batch=batch)

    return job_count, VerifyAssetImageJob.get_batch_admin_url(batch)
