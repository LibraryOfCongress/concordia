from django.db import transaction
from django.db.models import Case, IntegerField, Subquery, When

from concordia import models as concordia_models
from concordia.logging import ConcordiaLogger
from concordia.utils.celery import get_registered_task

structured_logger = ConcordiaLogger.get_logger(__name__)


def _reserved_asset_ids_subq():
    """
    Subquery of reserved asset IDs. Not filtered to the topic to avoid extra joins.
    """
    return concordia_models.AssetTranscriptionReservation.objects.values("asset_id")


def _eligible_reviewable_base_qs(topic, user=None):
    """
    Base queryset for reviewable assets within a topic, restricted to published
    objects and SUBMITTED status. Optionally excludes assets transcribed by user.
    """
    qs = concordia_models.Asset.objects.filter(
        item__project__topics=topic.id,
        item__project__published=True,
        item__published=True,
        published=True,
        transcription_status=concordia_models.TranscriptionStatus.SUBMITTED,
    ).select_related("item", "item__project")
    if user:
        qs = qs.exclude(transcription__user=user.id)
    return qs


def _next_seq_after(pk: int | None) -> int | None:
    """
    Resolve the sequence number for the given asset PK. Returns None if PK is
    falsy or the asset does not exist.
    """
    if not pk:
        return None
    return (
        concordia_models.Asset.objects.filter(pk=pk)
        .values_list("sequence", flat=True)
        .first()
    )


@transaction.atomic
def _find_reviewable_in_item(topic, user, *, item_id: str, after_asset_pk: int | None):
    """
    Short-circuit: find the next eligible SUBMITTED asset in the same item,
    ordered by sequence. Excludes reserved assets and locks the chosen row.
    """
    reserved_ids = _reserved_asset_ids_subq()
    base = (
        _eligible_reviewable_base_qs(topic, user)
        .filter(item__item_id=item_id)
        .exclude(pk__in=Subquery(reserved_ids))
    )

    after_seq = _next_seq_after(after_asset_pk)
    if after_seq is not None:
        base = base.filter(sequence__gt=after_seq)

    asset = (
        base.order_by("sequence")
        .select_for_update(skip_locked=True, of=("self",))
        .first()
    )

    if asset:
        structured_logger.debug(
            "Short-circuit hit: found reviewable within item.",
            event_code="reviewable_topic_shortcircuit_item_hit",
            topic=topic,
            user=user,
            item_id=item_id,
            after_asset_pk=after_asset_pk,
            asset=asset,
        )
    else:
        structured_logger.debug(
            "Short-circuit miss within item.",
            event_code="reviewable_topic_shortcircuit_item_miss",
            topic=topic,
            user=user,
            item_id=item_id,
            after_asset_pk=after_asset_pk,
        )
    return asset


@transaction.atomic
def _find_reviewable_in_project(
    topic, user, *, project_slug: str, after_asset_pk: int | None
):
    """
    Short-circuit: find the first eligible SUBMITTED asset in the same project,
    ordered by (item_id, sequence). Items have no explicit ordering; the item FK
    order is a stable proxy. Excludes reserved assets and locks the chosen row.
    """
    reserved_ids = _reserved_asset_ids_subq()
    base = (
        _eligible_reviewable_base_qs(topic, user)
        .filter(item__project__slug=project_slug)
        .exclude(pk__in=Subquery(reserved_ids))
    )

    asset = (
        base.order_by("item_id", "sequence")
        .select_for_update(skip_locked=True, of=("self",))
        .first()
    )

    if asset:
        structured_logger.debug(
            "Short-circuit hit: found reviewable within project.",
            event_code="reviewable_topic_shortcircuit_project_hit",
            topic=topic,
            user=user,
            project_slug=project_slug,
            after_asset_pk=after_asset_pk,
            asset=asset,
        )
    else:
        structured_logger.debug(
            "Short-circuit miss within project.",
            event_code="reviewable_topic_shortcircuit_project_miss",
            topic=topic,
            user=user,
            project_slug=project_slug,
            after_asset_pk=after_asset_pk,
        )
    return asset


def find_new_reviewable_topic_assets(topic, user=None):
    """
    Returns a queryset of assets in the given topic that are eligible for review
    caching.

    This excludes:
    - Assets with transcription_status not SUBMITTED
    - Assets currently reserved
    - Assets already present in the NextReviewableTopicAsset table
    - Optionally, assets transcribed by the given user

    Args:
        topic (Topic): The topic to filter assets by.
        user (User, optional): If provided, assets transcribed by this user will be
        excluded.

    Returns:
        QuerySet: Eligible assets ordered by sequence.
    """

    # Filtering this to the topic would be more costly than just getting all ids
    # in most cases because it requires joining the asset table to the item table to
    # the project table to the topic table.
    reserved_asset_ids = concordia_models.AssetTranscriptionReservation.objects.values(
        "asset_id"
    )
    next_asset_ids = concordia_models.NextReviewableTopicAsset.objects.filter(
        topic=topic
    ).values("asset_id")

    queryset = (
        concordia_models.Asset.objects.filter(
            item__project__topics=topic.id,
            item__project__published=True,
            item__published=True,
            published=True,
        )
        .filter(transcription_status=concordia_models.TranscriptionStatus.SUBMITTED)
        .exclude(pk__in=Subquery(reserved_asset_ids))
        .exclude(pk__in=Subquery(next_asset_ids))
        .order_by("sequence")
    )
    if user:
        queryset = queryset.exclude(transcription__user=user.id)
    return queryset


def find_next_reviewable_topic_assets(topic, user):
    """
    Returns cached reviewable assets for a topic that were not transcribed by the given
    user.

    This accesses the NextReviewableTopicAsset cache table and filters out any
    assets associated with the given user via the transcriber_ids field.

    Args:
        topic (Topic): The topic to filter assets by.
        user (User): The user requesting a reviewable asset.

    Returns:
        QuerySet: Cached assets
    """

    return concordia_models.NextReviewableTopicAsset.objects.filter(
        topic=topic
    ).exclude(transcriber_ids__contains=[user.id])


@transaction.atomic
def find_reviewable_topic_asset(topic, user):
    """
    Retrieves a single reviewable asset from the topic for the given user.

    Attempts to retrieve an asset from the cache table (NextReviewableTopicAsset).
    If no eligible asset is found, falls back to computing one directly from the
    Asset table and asynchronously schedules a background task to repopulate the cache.

    Ensures database row-level locking to prevent multiple concurrent consumers
    from selecting the same asset.

    Args:
        topic (Topic): The topic to retrieve an asset from.
        user (User): The user requesting the asset (used to exclude their own work).

    Returns:
        Asset or None: A locked asset eligible for review, or None if unavailable.
    """

    next_asset = (
        find_next_reviewable_topic_assets(topic, user)
        .select_for_update(skip_locked=True, of=("self",))
        .values_list("asset_id", flat=True)
        .first()
    )

    spawn_task = False
    if next_asset:
        asset_query = concordia_models.Asset.objects.filter(id=next_asset)
    else:
        # No asset in the NextReviewableTopicAsset table for this topic,
        # so fallback to manually finding one
        structured_logger.debug(
            "No cached assets available, falling back to manual lookup",
            event_code="reviewable_fallback_manual_lookup",
            topic=topic,
            user=user,
        )
        spawn_task = True
        asset_query = find_new_reviewable_topic_assets(topic, user)

    # select_for_update(of=("self",)) causes the row locking only to
    # apply to the Asset table, rather than also locking joined item table
    asset = (
        asset_query.select_for_update(skip_locked=True, of=("self",))
        .select_related("item", "item__project")
        .first()
    )

    if spawn_task:
        # Spawn a task to populate the table for this topic
        # We wait to do this until after getting an asset because otherwise there's a
        # a chance all valid assets get grabbed by the task and our query will return
        # nothing
        structured_logger.debug(
            "Spawned background task to populate cache",
            event_code="reviewable_cache_population_triggered",
            topic=topic,
            user=user,
        )
        populate_task = get_registered_task(
            "concordia.tasks.populate_next_reviewable_for_topic"
        )
        populate_task.delay(topic.id)

    return asset


def find_and_order_potential_reviewable_topic_assets(
    topic, user, project_slug, item_id, asset_pk
):
    """
    Retrieves and prioritizes cached reviewable assets for a user based on proximity.

    Orders results from NextReviewableTopicAsset by:
    - Whether the asset comes after the given asset in sequence
    - Whether the asset belongs to the same project
    - Whether the asset belongs to the same item

    Args:
        topic (Topic): The topic to filter assets by.
        user (User): The user requesting the next asset.
        project_slug (str): Slug of the original asset's project.
        item_id (str): Item ID of the original asset.
        asset_pk (int): Primary key of the original asset.

    Returns:
        QuerySet: Prioritized list of candidate assets.
    """

    potential_next_assets = find_next_reviewable_topic_assets(topic, user)

    # We'll favor assets which are in the same item or project as the original:
    potential_next_assets = potential_next_assets.annotate(
        same_project=Case(
            When(project_slug=project_slug, then=1),
            default=0,
            output_field=IntegerField(),
        ),
        same_item=Case(
            When(item_item_id=item_id, then=1), default=0, output_field=IntegerField()
        ),
        next_asset=Case(
            When(asset_id__gt=asset_pk, then=1), default=0, output_field=IntegerField()
        ),
    ).order_by("-next_asset", "-same_project", "-same_item", "sequence")

    return potential_next_assets


@transaction.atomic
def find_next_reviewable_topic_asset(
    topic, user, project_slug, item_id, original_asset_id
):
    """
    Retrieves the next best reviewable asset for a user within a topic.

    - If item_id is provided, first try to return the next eligible asset
      in that item by sequence (short-circuit).
    - Else if project_slug is provided, try to return the first eligible
      asset within that project (short-circuit).
    - Else fall back to the existing cache-backed path:

    Attempts to retrieve an asset from the cache table (NextReviewableTopicAsset).
    If no eligible asset is found, falls back to computing one directly from the
    Asset table and asynchronously schedules a background task to repopulate the cache.

    Ensures database row-level locking to prevent multiple concurrent consumers
    from selecting the same asset.

    Args:
        topic (Topic): The topic to find an asset in.
        user (User): The user requesting the asset.
        project_slug (str): Slug of the project the user is currently reviewing.
        item_id (str): ID of the item the user is currently reviewing.
        original_asset_id (int): ID of the asset the user just reviewed.

    Returns:
        Asset or None: A locked asset eligible for review, or None if unavailable.
    """
    try:
        after_pk = int(original_asset_id) if original_asset_id else None
    except (TypeError, ValueError):
        after_pk = None

    # Short-circuit: same item
    if item_id:
        asset = _find_reviewable_in_item(
            topic, user, item_id=item_id, after_asset_pk=after_pk
        )
        if asset:
            return asset

    # Short-circuit: same project
    if project_slug:
        asset = _find_reviewable_in_project(
            topic, user, project_slug=project_slug, after_asset_pk=after_pk
        )
        if asset:
            return asset

    # cache-backed selection, then manual fallback
    potential_next_assets = find_and_order_potential_reviewable_topic_assets(
        topic, user, project_slug, item_id, original_asset_id
    )
    asset_id = (
        potential_next_assets.select_for_update(skip_locked=True, of=("self",))
        .values_list("asset_id", flat=True)
        .first()
    )

    spawn_task = False
    if asset_id:
        asset_query = concordia_models.Asset.objects.filter(id=asset_id)
    else:
        # Since we had no potential next assets in the caching table, we have to check
        # the asset table directly.
        structured_logger.debug(
            "No cached assets matched, falling back to manual lookup",
            event_code="reviewable_next_fallback_manual",
            topic=topic,
            user=user,
        )
        spawn_task = True
        asset_query = find_new_reviewable_topic_assets(topic, user)
        asset_query = asset_query.annotate(
            same_project=Case(
                When(item__project__slug=project_slug, then=1),
                default=0,
                output_field=IntegerField(),
            ),
            same_item=Case(
                When(item__item_id=item_id, then=1),
                default=0,
                output_field=IntegerField(),
            ),
            next_asset=Case(
                When(id__gt=original_asset_id, then=1),
                default=0,
                output_field=IntegerField(),
            ),
        ).order_by("-next_asset", "-same_project", "-same_item", "sequence")

    asset = (
        asset_query.select_for_update(skip_locked=True, of=("self",))
        .select_related("item", "item__project")
        .first()
    )

    if spawn_task:
        # Spawn a task to populate the table for this topic
        # We wait to do this until after getting an asset because otherwise there's a
        # a chance all valid assets get grabbed by the task and our query will return
        # nothing
        structured_logger.debug(
            "Spawned background task to populate cache",
            event_code="reviewable_next_cache_population",
            topic=topic,
            user=user,
        )
        populate_task = get_registered_task(
            "concordia.tasks.populate_next_reviewable_for_topic"
        )
        populate_task.delay(topic.id)

    return asset


def find_invalid_next_reviewable_topic_assets(topic_id):
    """
    Returns a queryset of NextReviewableTopicAsset records that are no longer valid for
    review. This includes:
    - Assets with a transcription status other than SUBMITTED.
    - Assets currently reserved via AssetTranscriptionReservation.

    Args:
        topic_id (int): The ID of the topic to filter by.

    Returns:
        QuerySet: Invalid NextReviewableTopicAsset records.
    """
    reserved_asset_ids = concordia_models.AssetTranscriptionReservation.objects.filter(
        asset__item__project__topics=topic_id
    ).values("asset_id")

    status_filtered = concordia_models.NextReviewableTopicAsset.objects.exclude(
        asset__transcription_status=concordia_models.TranscriptionStatus.SUBMITTED
    ).filter(topic_id=topic_id)

    reserved_filtered = concordia_models.NextReviewableTopicAsset.objects.filter(
        topic_id=topic_id, asset_id__in=Subquery(reserved_asset_ids)
    )

    return (status_filtered | reserved_filtered).distinct()
