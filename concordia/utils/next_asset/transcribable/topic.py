from django.db import transaction
from django.db.models import Case, IntegerField, Q, Subquery, When

from concordia import models as concordia_models
from concordia.logging import ConcordiaLogger
from concordia.utils.celery import get_registered_task

structured_logger = ConcordiaLogger.get_logger(__name__)


def _reserved_asset_ids_subq():
    """
    Subquery of reserved asset IDs. Not filtered to topic to avoid extra joins.
    """
    return concordia_models.AssetTranscriptionReservation.objects.values("asset_id")


def _eligible_transcribable_base_qs(topic):
    """
    Base queryset for transcribable assets within a topic, restricted to
    published objects and the NOT_STARTED / IN_PROGRESS statuses.
    """
    return concordia_models.Asset.objects.filter(
        item__project__topics=topic.id,
        item__project__published=True,
        item__published=True,
        published=True,
        transcription_status__in=[
            concordia_models.TranscriptionStatus.NOT_STARTED,
            concordia_models.TranscriptionStatus.IN_PROGRESS,
        ],
    ).select_related("item", "item__project")


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


def _order_unstarted_first(qs):
    """
    Stable ordering that prefers NOT_STARTED over IN_PROGRESS, then by sequence.
    """
    return qs.annotate(
        unstarted=Case(
            When(
                transcription_status=concordia_models.TranscriptionStatus.NOT_STARTED,
                then=1,
            ),
            default=0,
            output_field=IntegerField(),
        )
    ).order_by("-unstarted", "sequence")


def _find_transcribable_in_item_for_topic(
    topic, *, item_id: str, after_asset_pk: int | None
):
    """
    Fast path: find the next transcribable asset in the SAME ITEM, constrained
    to the topic.

    Rules:
      - Asset must belong to a project that’s in this topic.
      - Exclude the current asset (never return the same one).
      - Advance by sequence within the item:
          (sequence > current_sequence)
          OR (sequence == current_sequence AND id > current_id)
      - **Return ONLY NOT_STARTED** here. (We defer IN_PROGRESS to later fallbacks so
        same-project NOT_STARTEDs are preferred over same-item IN_PROGRESS.)
      - Skip reserved assets.
      - Respect published flags.

    Returns:
        Asset | None
    """
    if not item_id:
        return None

    cur_seq = None
    if after_asset_pk:
        cur_seq = (
            concordia_models.Asset.objects.filter(pk=after_asset_pk)
            .values_list("sequence", flat=True)
            .first()
        )

    reserved_asset_ids = concordia_models.AssetTranscriptionReservation.objects.values(
        "asset_id"
    )

    base = concordia_models.Asset.objects.filter(
        item__item_id=item_id,
        item__project__topics=topic.id,
        item__published=True,
        item__project__published=True,
        published=True,
    ).exclude(pk__in=Subquery(reserved_asset_ids))

    if after_asset_pk:
        if cur_seq is not None:
            base = base.filter(
                Q(sequence__gt=cur_seq)
                | (Q(sequence=cur_seq) & Q(id__gt=after_asset_pk))
            )
        else:
            base = base.exclude(id=after_asset_pk)

    # ONLY NOT_STARTED in this short-circuit
    return (
        base.filter(
            transcription_status=concordia_models.TranscriptionStatus.NOT_STARTED
        )
        .order_by("sequence", "id")
        .first()
    )


def _find_transcribable_not_started_in_project_for_topic(
    topic, *, project_slug: str, exclude_item_id: str | None = None
):
    """
    Fast path: find the first NOT_STARTED asset in the SAME PROJECT within this topic.
    Optionally exclude the current item.

    Returns:
        Asset | None
    """
    if not project_slug:
        return None

    reserved_asset_ids = concordia_models.AssetTranscriptionReservation.objects.values(
        "asset_id"
    )

    base = concordia_models.Asset.objects.filter(
        item__project__topics=topic.id,
        item__project__slug=project_slug,
        item__published=True,
        item__project__published=True,
        published=True,
        transcription_status=concordia_models.TranscriptionStatus.NOT_STARTED,
    ).exclude(pk__in=Subquery(reserved_asset_ids))

    if exclude_item_id:
        base = base.exclude(item__item_id=exclude_item_id)

    return base.order_by("item__item_id", "sequence", "id").first()


def find_new_transcribable_topic_assets(topic):
    """
    Returns a queryset of assets in the given topic that are eligible for transcription
    caching.

    This excludes:
    - Assets with transcription_status not NOT_STARTED or IN_PROGRESS
    - Assets currently reserved
    - Assets already present in the NextTranscribableTopicAsset table

    Args:
        topic (Topic): The topic to filter assets by.

    Returns:
        QuerySet: Eligible assets ordered by sequence.
    """

    # Filtering this to the topic would be more costly than just getting all ids
    # in most cases because it requires joining the asset table to the item table to
    # the project table to the topic table.
    reserved_asset_ids = concordia_models.AssetTranscriptionReservation.objects.values(
        "asset_id"
    )
    next_asset_ids = concordia_models.NextTranscribableTopicAsset.objects.filter(
        topic=topic
    ).values("asset_id")

    return (
        concordia_models.Asset.objects.filter(
            item__project__topics=topic.id,
            item__project__published=True,
            item__published=True,
            published=True,
        )
        .filter(
            Q(transcription_status=concordia_models.TranscriptionStatus.NOT_STARTED)
            | Q(transcription_status=concordia_models.TranscriptionStatus.IN_PROGRESS)
        )
        .exclude(pk__in=Subquery(reserved_asset_ids))
        .exclude(pk__in=Subquery(next_asset_ids))
        .order_by("sequence")
    )


def find_next_transcribable_topic_assets(topic):
    """
    Returns all cached transcribable assets for a topic.

    This accesses the NextTranscribableTopicAsset cache table for the given topic.

    Args:
        topic (Topic): The topic to retrieve cached assets for.

    Returns:
        QuerySet: Cached assets
    """

    return concordia_models.NextTranscribableTopicAsset.objects.filter(topic=topic)


@transaction.atomic
def find_transcribable_topic_asset(topic):
    """
    Retrieves a single transcribable asset from the topic.

    Attempts to retrieve an asset from the cache table (NextTranscribableTopicAsset).
    If no eligible asset is found, falls back to computing one directly from the
    Asset table and asynchronously schedules a background task to repopulate the cache.

    Ensures database row-level locking to prevent multiple concurrent consumers
    from selecting the same asset.

    Args:
        topic (Topic): The topic to retrieve an asset from.

    Returns:
        Asset or None: A locked asset eligible for transcription, or None if
        unavailable.
    """

    next_asset = (
        find_next_transcribable_topic_assets(topic)
        .select_for_update(skip_locked=True, of=("self",))
        .values_list("asset_id", flat=True)
        .first()
    )

    spawn_task = False
    if next_asset:
        asset_query = concordia_models.Asset.objects.filter(id=next_asset)
    else:
        # No asset in the NextTranscribableTopicAsset table for this topic,
        # so fallback to manually finding one
        structured_logger.debug(
            "No cached assets available, falling back to manual lookup",
            event_code="transcribable_fallback_manual_lookup",
            topic=topic,
        )
        asset_query = find_new_transcribable_topic_assets(topic)
        spawn_task = True
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
            event_code="transcribable_cache_population_triggered",
            topic=topic,
        )
        populate_task = get_registered_task(
            "concordia.tasks.populate_next_transcribable_for_topic"
        )
        populate_task.delay(topic.id)
    return asset


def find_and_order_potential_transcribable_topic_assets(
    topic, project_slug, item_id, asset_pk
):
    """
    Retrieves and prioritizes cached transcribable assets based on proximity and status.

    Orders results from NextTranscribableTopicAsset by:
    - Whether the asset is in the NOT_STARTED state
    - Whether the asset belongs to the same project
    - Whether the asset belongs to the same item
    - Then by sequence and asset_id for stability

    Args:
        topic (Topic): The topic to filter assets by.
        project_slug (str): Slug of the original asset's project.
        item_id (str): Item ID of the original asset.
        asset_pk (int): Primary key of the original asset (not used to order first).

    Returns:
        QuerySet: Prioritized list of candidate assets.
    """

    potential_next_assets = find_next_transcribable_topic_assets(topic)

    potential_next_assets = potential_next_assets.annotate(
        unstarted=Case(
            When(
                transcription_status=concordia_models.TranscriptionStatus.NOT_STARTED,
                then=1,
            ),
            default=0,
            output_field=IntegerField(),
        ),
        same_project=Case(
            When(project_slug=project_slug, then=1),
            default=0,
            output_field=IntegerField(),
        ),
        same_item=Case(
            When(item_item_id=item_id, then=1),
            default=0,
            output_field=IntegerField(),
        ),
    ).order_by(
        "-unstarted",
        "-same_project",
        "-same_item",
        "sequence",
        "asset_id",
    )

    return potential_next_assets


@transaction.atomic
def find_next_transcribable_topic_asset(
    topic, project_slug, item_id, original_asset_id
):
    """
    Retrieves the next best transcribable asset for a user within a topic.

    Priority for short-circuit selection (before cache/fallback):
    1) If item_id is provided, return the next NOT_STARTED asset in that item
       by sequence (> the original asset's sequence when available).
    2) If project_slug is provided, return the first NOT_STARTED asset in that
       project (ordered by item_id, then sequence), constrained to the topic.
       This step avoids the original asset and the current item.

    If none of the above match, falls back to the cache-backed path (NOT_STARTED
    anywhere in the topic, avoiding the original asset and current item). If no cached
    match is available, compute manually and schedule a background task to repopulate.

    After exhausting NOT_STARTED options, select the next IN_PROGRESS asset in the
    same item (by sequence > original when available).

    Args:
        topic (Topic): The topic to find an asset in.
        project_slug (str): Slug of the project the user is currently transcribing.
        item_id (str): ID of the item the user is currently transcribing.
        original_asset_id (int): ID of the asset the user just transcribed.

    Returns:
        Asset or None: A locked asset eligible for transcription, or None if
        unavailable.
    """
    # Resolve "after sequence" only when the original asset belongs to the same item.
    after_seq = None
    if item_id and original_asset_id:
        try:
            orig = (
                concordia_models.Asset.objects.select_related("item")
                .only("id", "sequence", "item__item_id")
                .get(pk=original_asset_id)
            )
            if getattr(orig.item, "item_id", None) == item_id:
                after_seq = orig.sequence
        except concordia_models.Asset.DoesNotExist:
            after_seq = None

    reserved_asset_ids = concordia_models.AssetTranscriptionReservation.objects.values(
        "asset_id"
    )

    # Short-circuit: same item and NOT_STARTED after current sequence
    if item_id:
        qs = concordia_models.Asset.objects.filter(
            item__project__topics=topic.id,
            item__item_id=item_id,
            item__published=True,
            item__project__published=True,
            published=True,
            transcription_status=concordia_models.TranscriptionStatus.NOT_STARTED,
        ).exclude(pk__in=Subquery(reserved_asset_ids))
        if original_asset_id:
            qs = qs.exclude(pk=original_asset_id)
        if after_seq is not None:
            qs = qs.filter(
                Q(sequence__gt=after_seq)
                | (Q(sequence=after_seq) & Q(id__gt=original_asset_id))
            )
        asset = (
            qs.order_by("sequence", "id")
            .select_for_update(skip_locked=True, of=("self",))
            .select_related("item", "item__project")
            .first()
        )
        if asset:
            return asset

    # Short-circuit: same project and NOT_STARTED (topic-constrained),
    # avoiding the current item and original asset
    if project_slug:
        candidate = concordia_models.Asset.objects.filter(
            item__project__topics=topic.id,
            item__project__slug=project_slug,
            item__published=True,
            item__project__published=True,
            published=True,
            transcription_status=concordia_models.TranscriptionStatus.NOT_STARTED,
        ).exclude(pk__in=Subquery(reserved_asset_ids))
        if original_asset_id:
            candidate = candidate.exclude(pk=original_asset_id)
        if item_id:
            candidate = candidate.exclude(item__item_id=item_id)

        asset = (
            candidate.order_by("item__item_id", "sequence", "id")
            .select_for_update(skip_locked=True, of=("self",))
            .select_related("item", "item__project")
            .first()
        )
        if asset:
            return asset

    # Cache-backed selection (NOT_STARTED anywhere in the topic), then manual fallback.
    potential_next_assets = find_and_order_potential_transcribable_topic_assets(
        topic, project_slug, item_id, original_asset_id
    )
    if original_asset_id:
        potential_next_assets = potential_next_assets.exclude(
            asset_id=original_asset_id
        )
    if item_id:
        # Keep moving forward: avoid bouncing to the same item
        potential_next_assets = potential_next_assets.exclude(item_item_id=item_id)

    asset_id = (
        potential_next_assets.select_for_update(skip_locked=True, of=("self",))
        .values_list("asset_id", flat=True)
        .first()
    )

    spawn_task = False
    if asset_id:
        asset_query = concordia_models.Asset.objects.filter(id=asset_id)
    else:
        structured_logger.debug(
            "No cached assets matched, falling back to manual lookup",
            event_code="transcribable_next_fallback_manual",
            topic=topic,
        )
        spawn_task = True
        asset_query = find_new_transcribable_topic_assets(topic)
        if original_asset_id:
            asset_query = asset_query.exclude(pk=original_asset_id)
        if item_id:
            asset_query = asset_query.exclude(item__item_id=item_id)
        asset_query = asset_query.annotate(
            unstarted=Case(
                When(
                    transcription_status=concordia_models.TranscriptionStatus.NOT_STARTED,
                    then=1,
                ),
                default=0,
                output_field=IntegerField(),
            ),
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
        ).order_by(
            "-unstarted",
            "-same_project",
            "-same_item",
            "sequence",
            "id",
        )

    asset = (
        asset_query.select_for_update(skip_locked=True, of=("self",))
        .select_related("item", "item__project")
        .first()
    )
    if asset:
        if spawn_task:
            structured_logger.debug(
                "Spawned background task to populate cache",
                event_code="transcribable_next_cache_population",
                topic=topic,
            )
            populate_task = get_registered_task(
                "concordia.tasks.populate_next_transcribable_for_topic"
            )
            populate_task.delay(topic.id)
        return asset

    # Only now consider same-item IN_PROGRESS after current sequence
    if item_id:
        qs = concordia_models.Asset.objects.filter(
            item__project__topics=topic.id,
            item__item_id=item_id,
            item__published=True,
            item__project__published=True,
            published=True,
            transcription_status=concordia_models.TranscriptionStatus.IN_PROGRESS,
        ).exclude(pk__in=Subquery(reserved_asset_ids))
        if original_asset_id:
            qs = qs.exclude(pk=original_asset_id)
        if after_seq is not None:
            qs = qs.filter(
                Q(sequence__gt=after_seq)
                | (Q(sequence=after_seq) & Q(id__gt=original_asset_id))
            )
        asset = (
            qs.order_by("sequence", "id")
            .select_for_update(skip_locked=True, of=("self",))
            .select_related("item", "item__project")
            .first()
        )
        if asset:
            return asset

    return None


def find_invalid_next_transcribable_topic_assets(topic_id):
    """
    Returns a queryset of NextTranscribableTopicAsset records that are no longer valid
    for transcription. This includes:
    - Assets with a transcription status other than NOT_STARTED or IN_PROGRESS.
    - Assets currently reserved via AssetTranscriptionReservation.

    Args:
        topic_id (int): The ID of the topic to filter by.

    Returns:
        QuerySet: Invalid NextTranscribableTopicAsset records.
    """
    reserved_asset_ids = concordia_models.AssetTranscriptionReservation.objects.filter(
        asset__item__project__topics=topic_id
    ).values("asset_id")

    status_filtered = concordia_models.NextTranscribableTopicAsset.objects.filter(
        topic_id=topic_id
    ).exclude(
        asset__transcription_status__in=[
            concordia_models.TranscriptionStatus.NOT_STARTED,
            concordia_models.TranscriptionStatus.IN_PROGRESS,
        ]
    )

    reserved_filtered = concordia_models.NextTranscribableTopicAsset.objects.filter(
        topic_id=topic_id, asset_id__in=Subquery(reserved_asset_ids)
    )

    return (status_filtered | reserved_filtered).distinct()
