from typing import Dict

from django.db import transaction
from django.db.models import Case, IntegerField, Q, QuerySet, Subquery, When

from concordia import models as concordia_models
from concordia.logging import ConcordiaLogger
from concordia.utils.celery import get_registered_task

structured_logger = ConcordiaLogger.get_logger(__name__)


def _reserved_asset_ids_subq() -> "QuerySet[Dict[str, int]]":
    """
    Return a subquery of reserved asset identifiers.

    Behavior:
        Not filtered to the topic to avoid extra joins. Produces a subquery
        suitable for use with `Subquery(...)` and `exclude(pk__in=...)`
        clauses to filter out assets that currently have an active
        reservation.

    Returns:
        QuerySet[Dict[str, int]]: A queryset of dictionaries with a single key
            "asset_id" corresponding to reserved assets.
    """
    return concordia_models.AssetTranscriptionReservation.objects.values("asset_id")


def _eligible_transcribable_base_qs(
    topic: "concordia_models.Topic",
) -> "QuerySet[concordia_models.Asset]":
    """
    Build the base queryset of transcribable assets for a topic.

    Behavior:
        Restricts to published projects, items, and assets, and to assets whose
        transcription status is either `NOT_STARTED` or `IN_PROGRESS`.

    Args:
        topic (concordia_models.Topic): Topic scope for filtering.

    Returns:
        QuerySet[concordia_models.Asset]: Transcribable assets, with `item` and
            `item__project` selected via `select_related`.
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
    Resolve the sequence number for a given asset primary key.

    Behavior:
        Convenience utility for ordering logic when advancing within a series
        of assets.

    Args:
        pk (int | None): Asset primary key whose sequence to resolve.

    Returns:
        int | None: The asset's sequence number, or None if `pk` is falsy
            or the asset does not exist.
    """
    if not pk:
        return None
    return (
        concordia_models.Asset.objects.filter(pk=pk)
        .values_list("sequence", flat=True)
        .first()
    )


def _order_unstarted_first(
    qs: "QuerySet[concordia_models.Asset]",
) -> "QuerySet[concordia_models.Asset]":
    """
    Apply a stable ordering that prefers `NOT_STARTED` over `IN_PROGRESS`,
    then orders by `sequence`.

    Args:
        qs (QuerySet[concordia_models.Asset]): Base queryset to annotate and sort.

    Returns:
        QuerySet[concordia_models.Asset]: Annotated and ordered queryset with a
            transient `unstarted` field (1 for `NOT_STARTED`, else 0).
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
    topic: "concordia_models.Topic",
    *,
    item_id: str,
    after_asset_pk: int | None,
) -> "concordia_models.Asset | None":
    """
    Fast path: find the next transcribable asset in the same item, constrained
    to the topic.

    Behavior:
        - Asset must belong to a project that is in this topic.
        - Exclude the current asset.
        - Advance by `(sequence, id)` within the item.
        - Return only `NOT_STARTED` here (defer `IN_PROGRESS` to later fallbacks).
        - Skip reserved assets.
        - Respect published flags.

    Args:
        topic (concordia_models.Topic): Topic scope.
        item_id (str): Identifier of the item to stay within.
        after_asset_pk (int | None): Asset primary key to advance from.

    Returns:
        concordia_models.Asset | None: The next eligible asset, or None if none.
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
    topic: "concordia_models.Topic",
    *,
    project_slug: str,
    exclude_item_id: str | None = None,
) -> "concordia_models.Asset | None":
    """
    Fast path: find the first `NOT_STARTED` asset in the same project within
    this topic.

    Behavior:
        Optionally exclude the current item. Uses a stable ordering by
        `(item__item_id, sequence, id)`.

    Args:
        topic (concordia_models.Topic): Topic scope.
        project_slug (str): Slug of the project to stay within.
        exclude_item_id (str | None): If provided, exclude this item.

    Returns:
        concordia_models.Asset | None: The first eligible asset, or None if none.
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


def find_new_transcribable_topic_assets(
    topic: "concordia_models.Topic",
) -> "QuerySet[concordia_models.Asset]":
    """
    Return assets in a topic that are eligible to be added to the cache.

    Behavior:
        Builds the candidate set for the `NextTranscribableTopicAsset` cache by
        excluding assets that are not `NOT_STARTED` or `IN_PROGRESS`, assets
        already reserved, and assets already present in the cache.

    Args:
        topic (concordia_models.Topic): Topic to filter by.

    Returns:
        QuerySet[concordia_models.Asset]: Eligible assets ordered by `sequence`.
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


def find_next_transcribable_topic_assets(
    topic: "concordia_models.Topic",
) -> "QuerySet[concordia_models.NextTranscribableTopicAsset]":
    """
    Return all cached transcribable assets for a topic.

    Behavior:
        Reads from the `NextTranscribableTopicAsset` cache table for the
        given topic.

    Args:
        topic (concordia_models.Topic): Topic to retrieve cached assets for.

    Returns:
        QuerySet[concordia_models.NextTranscribableTopicAsset]: Cached candidates.
    """
    return concordia_models.NextTranscribableTopicAsset.objects.filter(topic=topic)


@transaction.atomic
def find_transcribable_topic_asset(
    topic: "concordia_models.Topic",
) -> "concordia_models.Asset | None":
    """
    Retrieve a single transcribable asset from the topic.

    Behavior:
        First attempts to select a cached asset from
        `NextTranscribableTopicAsset`. If none is available, falls back to a
        direct query over `Asset` and triggers a background task to replenish
        the cache.

    Concurrency:
        Uses `select_for_update(skip_locked=True, of=("self",))` so only the
        `Asset` row is locked and concurrent consumers skip locked rows.

    Args:
        topic (concordia_models.Topic): Topic to search within.

    Returns:
        concordia_models.Asset | None: A locked eligible asset, or None if
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
    topic: "concordia_models.Topic",
    project_slug: str,
    item_id: str,
    asset_pk: int,
) -> "QuerySet[concordia_models.NextTranscribableTopicAsset]":
    """
    Retrieve and prioritize cached transcribable assets based on proximity
    and status.

    Behavior:
        Orders cached candidates from `NextTranscribableTopicAsset` to prefer:
        - `NOT_STARTED` over `IN_PROGRESS` (via transient `unstarted` flag),
        - same project,
        - same item,
        then by `sequence` and `asset_id` for stability.

    Annotations added to each row (transient fields):
        - unstarted (int): 1 if transcription status is `NOT_STARTED`, else 0.
        - same_project (int): 1 if the candidate shares `project_slug`, else 0.
        - same_item (int): 1 if the candidate shares `item_id`, else 0.

    Args:
        topic (concordia_models.Topic): Topic to filter by.
        project_slug (str): Slug of the original asset's project.
        item_id (str): Item identifier of the original asset.
        asset_pk (int): Primary key of the original asset.

    Returns:
        QuerySet[concordia_models.NextTranscribableTopicAsset]: Prioritized
            cached candidates.
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
    topic: "concordia_models.Topic",
    project_slug: str,
    item_id: str,
    original_asset_id: int | None,
) -> "concordia_models.Asset | None":
    """
    Retrieve the next best transcribable asset within a topic.

    Priority for short-circuit selection (before cache and fallback):
        1) If `item_id` is provided, return the next `NOT_STARTED` asset in
           that item by sequence (strictly after the original asset when known).
        2) If `project_slug` is provided, return the first `NOT_STARTED` asset
           in that project (ordered by item id, then sequence), excluding the
           current item to keep moving forward.

    If none of the above match, fall back to the cache-backed path:
        Attempts to retrieve a candidate from `NextTranscribableTopicAsset`. If
        none is found, compute from `Asset` and trigger cache population.

    After exhausting `NOT_STARTED` options, consider `IN_PROGRESS` assets in the
    same item (strictly after the original when known).

    Concurrency:
        Uses `select_for_update(skip_locked=True, of=("self",))` to avoid
        double-assignments across concurrent consumers.

    Args:
        topic (concordia_models.Topic): Topic to search within.
        project_slug (str): Slug of the current project.
        item_id (str): Identifier of the current item.
        original_asset_id (int | None): Identifier of the asset just transcribed.

    Returns:
        concordia_models.Asset | None: A locked eligible asset, or None if
            unavailable.
    """
    # Resolve original context safely (int or digit-string only)
    after_seq = None
    orig = None
    orig_item_id = None
    orig_id_valid = isinstance(original_asset_id, int) or (
        isinstance(original_asset_id, str) and original_asset_id.isdigit()
    )
    if orig_id_valid:
        try:
            orig = (
                concordia_models.Asset.objects.select_related("item")
                .only("id", "sequence", "item__item_id")
                .get(pk=original_asset_id)
            )
            orig_item_id = getattr(orig.item, "item_id", None)
            # Keep sequence handy for same-item gating in any path
            after_seq = orig.sequence
        except concordia_models.Asset.DoesNotExist:
            orig = None
            orig_item_id = None
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
        if orig_id_valid:
            qs = qs.exclude(pk=original_asset_id)
        if after_seq is not None and orig_item_id == item_id:
            qs = qs.filter(
                Q(sequence__gt=after_seq)
                | (Q(sequence=after_seq) & Q(id__gt=int(original_asset_id)))
            )
        asset = (
            qs.order_by("sequence", "id")
            .select_for_update(skip_locked=True, of=("self",))
            .select_related("item", "item__project")
            .first()
        )
        if asset:
            return asset

    # Short-circuit: same project and NOT_STARTED (topic-constrained)
    if project_slug:
        candidate = concordia_models.Asset.objects.filter(
            item__project__topics=topic.id,
            item__project__slug=project_slug,
            item__published=True,
            item__project__published=True,
            published=True,
            transcription_status=concordia_models.TranscriptionStatus.NOT_STARTED,
        ).exclude(pk__in=Subquery(reserved_asset_ids))
        if orig_id_valid:
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

    # Cache-backed selection (NOT_STARTED anywhere), then manual fallback.
    potential_next_assets = find_and_order_potential_transcribable_topic_assets(
        topic, project_slug, item_id, original_asset_id
    )
    if orig_id_valid:
        potential_next_assets = potential_next_assets.exclude(
            asset_id=original_asset_id
        )
    if item_id:
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
        if orig_id_valid:
            asset_query = asset_query.exclude(pk=original_asset_id)
        if item_id:
            asset_query = asset_query.exclude(item__item_id=item_id)
        # If we know the original's item/seq, keep moving forward within that item
        if orig_item_id and after_seq is not None:
            asset_query = asset_query.exclude(
                Q(item__item_id=orig_item_id, sequence__lte=after_seq)
            )

        # Prefer same project and same item; if item_id is blank, prefer original's item
        ref_item_id = item_id or orig_item_id
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
                When(item__item_id=ref_item_id, then=1),
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
        if orig_id_valid:
            qs = qs.exclude(pk=original_asset_id)
        if after_seq is not None and orig_item_id == item_id:
            qs = qs.filter(
                Q(sequence__gt=after_seq)
                | (Q(sequence=after_seq) & Q(id__gt=int(original_asset_id)))
            )
        asset = (
            qs.order_by("sequence", "id")
            .select_for_update(skip_locked=True, of=("self",))
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

    return None


def find_invalid_next_transcribable_topic_assets(
    topic_id: int,
) -> "QuerySet[concordia_models.NextTranscribableTopicAsset]":
    """
    Return cached rows that are invalid for transcription for a topic.

    Behavior:
        Identifies `NextTranscribableTopicAsset` rows that are no longer valid
        because the underlying asset is neither `NOT_STARTED` nor
        `IN_PROGRESS`, or because the asset is currently reserved.

    Args:
        topic_id (int): Identifier of the topic.

    Returns:
        QuerySet[concordia_models.NextTranscribableTopicAsset]: Distinct invalid
            cache rows.
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
