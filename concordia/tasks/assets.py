import os.path
from logging import getLogger
from tempfile import NamedTemporaryFile

import requests
from more_itertools.more import chunked

from concordia.logging import ConcordiaLogger
from concordia.models import Asset
from concordia.storage import ASSET_STORAGE

from ..celery import app as celery_app

logger = getLogger(__name__)
structured_logger = ConcordiaLogger.get_logger(__name__)


@celery_app.task
def calculate_difficulty_values(asset_qs=None):
    """
    Calculate the difficulty scores for the provided AssetQuerySet and update
    the Asset records for changed difficulty values
    """

    if asset_qs is None:
        asset_qs = Asset.objects.published()

    asset_qs = asset_qs.add_contribution_counts()

    updated_count = 0

    # We'll process assets in chunks using an iterator to avoid saving objects
    # which will never be used again in memory. We will find assets which have a
    # difficulty value which is not the same as the value stored in the database
    # and pass them to bulk_update() to be saved in a single query.
    for asset_chunk in chunked(asset_qs.iterator(), 500):
        changed_assets = []

        for asset in asset_chunk:
            difficulty = asset.transcription_count * (
                asset.transcriber_count + asset.reviewer_count
            )
            if difficulty != asset.difficulty:
                asset.difficulty = difficulty
                changed_assets.append(asset)

        if changed_assets:
            # We will only save the new difficulty score both for performance
            # and to avoid any possibility of race conditions causing stale data
            # to be saved:
            Asset.objects.bulk_update(changed_assets, ["difficulty"])
            updated_count += len(changed_assets)

    return updated_count


@celery_app.task
def populate_asset_years():
    """
    Pull out date info from raw Item metadata and populate it for each Asset
    """

    asset_qs = Asset.objects.prefetch_related("item")

    updated_count = 0

    for asset_chunk in chunked(asset_qs, 500):
        changed_assets = []

        for asset in asset_chunk:
            metadata = asset.item.metadata

            year = None
            for date_outer in metadata["item"]["dates"]:
                for date_inner in date_outer.keys():
                    year = date_inner
                    break  # We don't support multiple values

            if asset.year != year:
                asset.year = year
                changed_assets.append(asset)

        if changed_assets:
            Asset.objects.bulk_update(changed_assets, ["year"])
            updated_count += len(changed_assets)

    return updated_count


@celery_app.task(ignore_result=True)
def fix_storage_images(campaign_slug=None, asset_start_id=None):
    if campaign_slug:
        from concordia.models import Campaign

        campaign = Campaign.objects.get(slug=campaign_slug)
        asset_queryset = Asset.objects.filter(item__project__campaign=campaign)
    else:
        asset_queryset = Asset.objects.all()

    if asset_start_id:
        asset_queryset = asset_queryset.filter(id__gte=asset_start_id)

    count = 0
    full_count = asset_queryset.count()
    logger.debug("Checking storage image on %s assets", full_count)
    for asset in asset_queryset.order_by("id"):
        count += 1
        if asset.storage_image:
            if not asset.storage_image.storage.exists(asset.storage_image.name):
                logger.info("Storage image does not exist for %s (%s)", asset, asset.id)
                item = asset.item
                download_url = asset.download_url
                asset_filename = os.path.join(
                    item.project.campaign.slug,
                    item.project.slug,
                    item.item_id,
                    "%d.jpg" % asset.sequence,
                )
                try:
                    with NamedTemporaryFile(mode="x+b") as temp_file:
                        resp = requests.get(download_url, stream=True, timeout=30)
                        resp.raise_for_status()

                        for chunk in resp.iter_content(chunk_size=256 * 1024):
                            temp_file.write(chunk)

                        # Rewind the tempfile back to the first byte so we can
                        temp_file.flush()
                        temp_file.seek(0)

                        ASSET_STORAGE.save(asset_filename, temp_file)

                except Exception:
                    logger.exception(
                        "Unable to download %s to %s", download_url, asset_filename
                    )
                    raise
                logger.info("Storage image downloaded for  %s (%s)", asset, asset.id)
        logger.debug("Storage image checked for %s (%s)", asset, asset.id)
        logger.debug("%s / %s (%s%%)", count, full_count, str(count / full_count * 100))
