from logging import getLogger
from typing import Optional

import requests
from celery import group
from django.db import transaction
from django.db.models import Q

from concordia.logging import ConcordiaLogger
from concordia.models import Item

from ..celery import app as celery_app

logger = getLogger(__name__)
structured_logger = ConcordiaLogger.get_logger(__name__)

# TODO: remove download_item_thumbnail_task once `item.thumbnail_url` is removed


@celery_app.task(
    bind=True,
    autoretry_for=(requests.RequestException,),
    retry_backoff=5,
    retry_kwargs={"max_retries": 5, "countdown": 5},
)
def download_item_thumbnail_task(
    self,
    item_id: int,
    force: bool = False,
) -> str:
    """
    Fetch an item and ensure its thumbnail image is populated.

    The item's ``thumbnail_url`` field is used as the source of the download.

    Args:
        item_id: Primary key of the item to process.
        force: Overwrite an existing thumbnail if true.

    Returns:
        Storage path of the saved image or a skip message.

    Raises:
        ValueError: If ``Item.thumbnail_url`` is unavailable.
        requests.RequestException: For network errors (auto-retried).
    """
    from importer.tasks.items import download_and_set_item_thumbnail

    with transaction.atomic():
        item = (
            Item.objects.select_for_update(of=("self",))
            .only("id", "thumbnail_url", "thumbnail_image", "item_id")
            .get(pk=item_id)
        )

    src_url = item.thumbnail_url
    if not src_url:
        msg = "No thumbnail URL available."
        logger.info("download_item_thumbnail_task: %s item_id=%s", msg, item_id)
        return msg

    return download_and_set_item_thumbnail(item, src_url, force=force)


# TODO: remove download_missing_thumbnails_task once `item.thumbnail_url` is removed


@celery_app.task(bind=True)
def download_missing_thumbnails_task(
    self,
    project_id: Optional[int] = None,
    batch_size: int = 10,
    limit: Optional[int] = None,
    force: bool = False,
) -> int:
    """
    Spawn per-item download tasks for items missing thumbnails in chunks.

    This finds items that have a non-empty ``thumbnail_url`` but no stored
    ``thumbnail_image``. It then executes per-item tasks in chunks of
    ``batch_size``, waiting for each chunk to finish before starting the next.

    Args:
        project_id: Optional project filter.
        batch_size: Number of parallel tasks per wave.
        limit: Optional cap on total items processed.
        force: Overwrite existing thumbnails if true.

    Returns:
        Count of items scheduled or processed.
    """
    qs = Item.objects.all()

    if project_id is not None:
        qs = qs.filter(project_id=project_id)

    qs = qs.filter(
        Q(thumbnail_url__isnull=False)
        & ~Q(thumbnail_url="")
        & (Q(thumbnail_image__isnull=True) | Q(thumbnail_image=""))
    ).order_by("pk")

    if limit is not None:
        qs = qs[:limit]

    ids = list(qs.values_list("pk", flat=True))
    total = len(ids)
    if total == 0:
        logger.info("download_missing_thumbnails_task: nothing to do.")
        return 0

    # Process in waves of `batch_size`, waiting between waves.
    for i in range(0, total, batch_size):
        chunk = ids[i : i + batch_size]
        task_group = group(
            download_item_thumbnail_task.s(item_id, force=force) for item_id in chunk
        )
        result = task_group.apply_async()
        # Block this task until the chunk finishes; then schedule next.
        result.get(disable_sync_subtasks=False)

    logger.info(
        "download_missing_thumbnails_task: processed %s items in chunks of %s",
        total,
        batch_size,
    )
    return total
