from typing import Dict

from django.db import transaction
from django.db.models import Case, IntegerField, Q, QuerySet, Subquery, When

from concordia import models as concordia_models
from concordia.logging import ConcordiaLogger
from concordia.utils.celery import get_registered_task

structured_logger = ConcordiaLogger.get_logger(__name__)


def _reserved_asset_ids_subq(
    campaign: concordia_models.Campaign,
) -> "QuerySet[Dict[str, int]]":
    """
    Return a subquery of reserved asset identifiers for a campaign.

    Behavior:
        Produces a subquery suitable for use with `Subquery(...)` and
        `exclude(pk__in=...)` clauses to filter out assets that currently have
        an active reservation.

    Args:
        campaign (concordia_models.Campaign): Campaign whose reserved assets
            should be excluded.

    Returns:
        QuerySet[Dict[str, int]]: A queryset of dictionaries with a single key
            "asset_id" corresponding to reserved assets.
    """
    return concordia_models.AssetTranscriptionReservation.objects.filter(
        asset__campaign=campaign
    ).values("asset_id")


def _eligible_transcribable_base_qs(
    campaign: concordia_models.Campaign,
) -> "QuerySet[concordia_models.Asset]":
    """
    Build the base queryset of transcribable assets for a campaign.

    Behavior:
        Restricts to published projects, items, and assets, and to assets whose
        transcription status is either `NOT_STARTED` or `IN_PROGRESS`.

    Args:
        campaign (concordia_models.Campaign): Campaign scope for filtering.

    Returns:
        QuerySet[concordia_models.Asset]: Transcribable assets, with `item` and
            `item__project` selected via `select_related`.
    """
    return concordia_models.Asset.objects.filter(
        campaign_id=campaign.id,
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


@transaction.atomic
def _find_transcribable_in_item(
    campaign: concordia_models.Campaign,
    *,
    item_id: str,
    after_asset_pk: int | None,
) -> "concordia_models.Asset | None":
    """
    Fast path: find the next transcribable asset in the same item.

    Behavior:
        - Exclude the current asset.
        - Advance by `(sequence, id)` within the item.
        - Return only `NOT_STARTED` here (defer `IN_PROGRESS` to later fallbacks).
        - Skip reserved assets.
        - Respect published flags on campaign, project, item, and asset.

    Args:
        campaign (concordia_models.Campaign): Campaign scope.
        item_id (str): Identifier of the item to stay within.
        after_asset_pk (int | None): Asset primary key to advance from.

    Returns:
        concordia_models.Asset | None: The next eligible asset, or None if none.
    """
    if not item_id:
        return None

    # Find current sequence to advance correctly within the item
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
        item__published=True,
        item__project__published=True,
        published=True,
        campaign_id=campaign.id,
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


def _find_transcribable_not_started_in_project(
    campaign: concordia_models.Campaign,
    *,
    project_slug: str,
    exclude_item_id: str | None = None,
) -> "concordia_models.Asset | None":
    """
    Fast path: find the first `NOT_STARTED` asset in the same project.

    Behavior:
        Allows different items (optionally excluding the current item to avoid
        bouncing back). Uses a stable ordering by `(item_id, sequence, id)`.

    Args:
        campaign (concordia_models.Campaign): Campaign scope.
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
        campaign_id=campaign.id,
        item__project__slug=project_slug,
        item__published=True,
        item__project__published=True,
        published=True,
        transcription_status=concordia_models.TranscriptionStatus.NOT_STARTED,
    ).exclude(pk__in=Subquery(reserved_asset_ids))

    if exclude_item_id:
        base = base.exclude(item__item_id=exclude_item_id)

    return base.order_by("item__item_id", "sequence", "id").first()


def find_new_transcribable_campaign_assets(
    campaign: concordia_models.Campaign,
) -> "QuerySet[concordia_models.Asset]":
    """
    Return assets in a campaign that are eligible to be added to the cache.

    Behavior:
        Builds the candidate set for the `NextTranscribableCampaignAsset` cache
        by excluding assets that are not `NOT_STARTED` or `IN_PROGRESS`, assets
        already reserved, and assets already present in the cache.

    Args:
        campaign (concordia_models.Campaign): Campaign to filter by.

    Returns:
        QuerySet[concordia_models.Asset]: Eligible assets ordered by `sequence`.
    """
    reserved_asset_ids = concordia_models.AssetTranscriptionReservation.objects.filter(
        asset__campaign=campaign
    ).values("asset_id")
    next_asset_ids = concordia_models.NextTranscribableCampaignAsset.objects.filter(
        campaign=campaign
    ).values("asset_id")

    return (
        concordia_models.Asset.objects.filter(
            campaign_id=campaign.id,
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


def find_next_transcribable_campaign_assets(
    campaign: concordia_models.Campaign,
) -> "QuerySet[concordia_models.NextTranscribableCampaignAsset]":
    """
    Return all cached transcribable assets for a campaign.

    Behavior:
        Reads from the `NextTranscribableCampaignAsset` cache table for the
        given campaign.

    Args:
        campaign (concordia_models.Campaign): Campaign to retrieve cached assets for.

    Returns:
        QuerySet[concordia_models.NextTranscribableCampaignAsset]: Cached candidates.
    """
    return concordia_models.NextTranscribableCampaignAsset.objects.filter(
        campaign=campaign
    )


@transaction.atomic
def find_transcribable_campaign_asset(
    campaign: concordia_models.Campaign,
) -> "concordia_models.Asset | None":
    """
    Retrieve a single transcribable asset from the campaign.

    Behavior:
        First attempts to select a cached asset from
        `NextTranscribableCampaignAsset`. If none is available, falls back to a
        direct query over `Asset` and triggers a background task to replenish
        the cache.

    Concurrency:
        Uses `select_for_update(skip_locked=True, of=("self",))` so only the
        `Asset` row is locked and concurrent consumers skip locked rows.

    Args:
        campaign (concordia_models.Campaign): Campaign to search within.

    Returns:
        concordia_models.Asset | None: A locked eligible asset, or None if
            unavailable.
    """
    next_asset = (
        find_next_transcribable_campaign_assets(campaign)
        .select_for_update(skip_locked=True, of=("self",))
        .values_list("asset_id", flat=True)
        .first()
    )

    spawn_task = False
    if next_asset:
        asset_query = concordia_models.Asset.objects.filter(id=next_asset)
    else:
        # No asset in the NextTranscribableCampaignAsset table for this campaign,
        # so fallback to manually finding on
        structured_logger.debug(
            "No cached assets available, falling back to manual lookup",
            event_code="transcribable_fallback_manual_lookup",
            campaign=campaign,
        )
        asset_query = find_new_transcribable_campaign_assets(campaign)
        spawn_task = True
    # select_for_update(of=("self",)) causes the row locking only to
    # apply to the Asset table, rather than also locking joined item table
    asset = (
        asset_query.select_for_update(skip_locked=True, of=("self",))
        .select_related("item", "item__project")
        .first()
    )
    if spawn_task:
        # Spawn a task to populate the table for this campaign
        # We wait to do this until after getting an asset because otherwise there's a
        # a chance all valid assets get grabbed by the task and our query will return
        # nothing
        structured_logger.debug(
            "Spawned background task to populate cache",
            event_code="transcribable_cache_population_triggered",
            campaign=campaign,
        )
        populate_task = get_registered_task(
            "concordia.tasks.populate_next_transcribable_for_campaign"
        )
        populate_task.delay(campaign.id)
    return asset


def find_and_order_potential_transcribable_campaign_assets(
    campaign: concordia_models.Campaign,
    project_slug: str,
    item_id: str,
    asset_pk: int,
) -> "QuerySet[concordia_models.NextTranscribableCampaignAsset]":
    """
    Retrieve and prioritize cached transcribable assets based on proximity
    and status.

    Behavior:
        Orders cached candidates from `NextTranscribableCampaignAsset` to prefer:
        - `NOT_STARTED` over `IN_PROGRESS` (via transient `unstarted` flag),
        - same project,
        - same item,
        then by `sequence` and `asset_id` for stability.

    Annotations added to each row (transient fields):
        - unstarted (int): 1 if transcription status is `NOT_STARTED`, else 0.
        - same_project (int): 1 if the candidate shares `project_slug`, else 0.
        - same_item (int): 1 if the candidate shares `item_id`, else 0.

    Args:
        campaign (concordia_models.Campaign): Campaign to filter by.
        project_slug (str): Slug of the original asset's project.
        item_id (str): Item identifier of the original asset.
        asset_pk (int): Primary key of the original asset.

    Returns:
        QuerySet[concordia_models.NextTranscribableCampaignAsset]: Prioritized
            cached candidates.
    """
    potential_next_assets = find_next_transcribable_campaign_assets(campaign)

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
def find_next_transcribable_campaign_asset(
    campaign: concordia_models.Campaign,
    project_slug: str,
    item_id: str,
    original_asset_id: int | None,
) -> "concordia_models.Asset | None":
    """
    Retrieve the next best transcribable asset within a campaign.

    Priority for short-circuit selection (before cache and fallback):
        1) If `item_id` is provided, return the next `NOT_STARTED` asset in
           that item by sequence (strictly after the original asset when known).
        2) If `project_slug` is provided, return the first `NOT_STARTED` asset
           in that project (ordered by item id, then sequence), excluding the
           current item to keep moving forward.

    If none of the above match, fall back to the cache-backed path:
        Attempts to retrieve a candidate from `NextTranscribableCampaignAsset`. If
        none is found, compute from `Asset` and trigger cache population.

    After exhausting `NOT_STARTED` options, consider `IN_PROGRESS` assets in the
    same item (strictly after the original when known).

    Concurrency:
        Uses `select_for_update(skip_locked=True, of=("self",))` to avoid
        double-assignments across concurrent consumers.

    Args:
        campaign (concordia_models.Campaign): Campaign to search within.
        project_slug (str): Slug of the current project.
        item_id (str): Identifier of the current item.
        original_asset_id (int | None): Identifier of the asset just transcribed.

    Returns:
        concordia_models.Asset | None: A locked eligible asset, or None if
            unavailable.
    """
    # Normalize original_asset_id for safe use in filters/comparisons
    try:
        original_pk = int(original_asset_id) if original_asset_id is not None else None
    except (TypeError, ValueError):
        original_pk = None

    # Resolve "after sequence" only when the original asset belongs to the same item.
    after_seq = None
    if item_id and original_pk is not None:
        try:
            orig = (
                concordia_models.Asset.objects.select_related("item")
                .only("id", "sequence", "item__item_id")
                .get(pk=original_pk)
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
            campaign_id=campaign.id,
            item__item_id=item_id,
            item__published=True,
            item__project__published=True,
            published=True,
            transcription_status=concordia_models.TranscriptionStatus.NOT_STARTED,
        ).exclude(pk__in=Subquery(reserved_asset_ids))
        if original_pk is not None:
            qs = qs.exclude(pk=original_pk)
        if after_seq is not None:
            qs = qs.filter(
                Q(sequence__gt=after_seq)
                | (Q(sequence=after_seq) & Q(id__gt=original_pk))
            )
        asset = (
            qs.order_by("sequence", "id")
            .select_for_update(skip_locked=True, of=("self",))
            .select_related("item", "item__project")
            .first()
        )
        if asset:
            return asset

    # Short-circuit: same project and NOT_STARTED (avoid current item and original)
    if project_slug:
        candidate = concordia_models.Asset.objects.filter(
            campaign_id=campaign.id,
            item__project__slug=project_slug,
            item__published=True,
            item__project__published=True,
            published=True,
            transcription_status=concordia_models.TranscriptionStatus.NOT_STARTED,
        ).exclude(pk__in=Subquery(reserved_asset_ids))
        if original_pk is not None:
            candidate = candidate.exclude(pk=original_pk)
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

    # Cache-backed selection (NOT_STARTED), then manual fallback (also NOT_STARTED)
    potential_next_assets = find_and_order_potential_transcribable_campaign_assets(
        campaign, project_slug, item_id, original_asset_id
    )
    if original_pk is not None:
        potential_next_assets = potential_next_assets.exclude(asset_id=original_pk)
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
            campaign=campaign,
        )
        spawn_task = True
        asset_query = find_new_transcribable_campaign_assets(campaign)
        if original_pk is not None:
            asset_query = asset_query.exclude(pk=original_pk)
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
                campaign=campaign,
            )
            populate_task = get_registered_task(
                "concordia.tasks.populate_next_transcribable_for_campaign"
            )
            populate_task.delay(campaign.id)
        return asset

    # Only now consider same-item IN_PROGRESS after current sequence
    if item_id:
        qs = concordia_models.Asset.objects.filter(
            campaign_id=campaign.id,
            item__item_id=item_id,
            item__published=True,
            item__project__published=True,
            published=True,
            transcription_status=concordia_models.TranscriptionStatus.IN_PROGRESS,
        ).exclude(pk__in=Subquery(reserved_asset_ids))
        if original_pk is not None:
            qs = qs.exclude(pk=original_pk)
        if after_seq is not None:
            qs = qs.filter(
                Q(sequence__gt=after_seq)
                | (Q(sequence=after_seq) & Q(id__gt=original_pk))
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


def find_invalid_next_transcribable_campaign_assets(
    campaign_id: int,
) -> "QuerySet[concordia_models.NextTranscribableCampaignAsset]":
    """
    Return cached rows that are invalid for transcription for a campaign.

    Behavior:
        Identifies `NextTranscribableCampaignAsset` rows that are no longer valid
        because the underlying asset is neither `NOT_STARTED` nor `IN_PROGRESS`,
        or because the asset is currently reserved.

    Args:
        campaign_id (int): Identifier of the campaign.

    Returns:
        QuerySet[concordia_models.NextTranscribableCampaignAsset]: Distinct invalid
            cache rows.
    """
    reserved_asset_ids = concordia_models.AssetTranscriptionReservation.objects.filter(
        asset__campaign_id=campaign_id
    ).values("asset_id")

    # Assets with transcription_status not eligible for transcription
    status_filtered = concordia_models.NextTranscribableCampaignAsset.objects.filter(
        campaign_id=campaign_id
    ).exclude(
        asset__transcription_status__in=[
            concordia_models.TranscriptionStatus.NOT_STARTED,
            concordia_models.TranscriptionStatus.IN_PROGRESS,
        ]
    )

    # Assets that are reserved
    reserved_filtered = concordia_models.NextTranscribableCampaignAsset.objects.filter(
        campaign_id=campaign_id, asset_id__in=Subquery(reserved_asset_ids)
    )

    return (status_filtered | reserved_filtered).distinct()
