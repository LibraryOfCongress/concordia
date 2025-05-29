from itertools import islice

from importer.models import VerifyAssetImageJob
from importer.tasks.images import batch_verify_asset_images_task

BATCH_SIZE = 100


def create_verify_asset_image_job_batch(asset_pks, batch):
    # asset_pks: list of asset ids to generate jobs for
    # batch: uuid to group jobs together as a batch; unrelated to the batch size

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
