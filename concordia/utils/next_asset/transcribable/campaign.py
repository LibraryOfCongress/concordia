from django.db import transaction
from django.db.models import Case, IntegerField, Q, Subquery, When

from concordia import models as concordia_models
from concordia.logging import ConcordiaLogger
from concordia.utils.celery import get_registered_task

structured_logger = ConcordiaLogger.get_logger(__name__)


def _reserved_asset_ids_subq(campaign):
    """
    Subquery of reserved asset IDs for the campaign. Used to exclude assets
    that have an active reservation.
    """
    return concordia_models.AssetTranscriptionReservation.objects.filter(
        asset__campaign=campaign
    ).values("asset_id")


def _eligible_transcribable_base_qs(campaign):
    """
    Base queryset for transcribable assets in a campaign, restricted to
    published objects and the correct transcription_status values.
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


@transaction.atomic
def _find_transcribable_in_item(campaign, *, item_id: str, after_asset_pk: int | None):
    """
    Fast path: find the next transcribable asset in the SAME ITEM.

    Rules:
      - Exclude the current asset (never return the same one).
      - Advance by sequence within the item:
          (sequence > current_sequence)
          OR (sequence == current_sequence AND id > current_id)
      - **Return ONLY NOT_STARTED** here. (We defer IN_PROGRESS to later fallbacks so
        same-project NOT_STARTEDs are preferred over same-item IN_PROGRESS.)
      - Skip reserved assets.
      - Respect published flags on campaign/project/item/asset.

    Returns:
        Asset | None
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
    campaign, *, project_slug: str, exclude_item_id: str | None = None
):
    """
    Fast path: find the first NOT_STARTED asset in the SAME PROJECT (different items
    allowed; we optionally exclude the current item to avoid bouncing back).

    Ordering across items isn't material for current tests (items have no defined
    order), so we use a stable ordering by (item_id, sequence, id).

    Returns:
        Asset | None
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


def find_new_transcribable_campaign_assets(campaign):
    """
    Returns a queryset of assets in the given campaign that are eligible for
    transcription caching.

    This excludes:
    - Assets with transcription_status not NOT_STARTED or IN_PROGRESS
    - Assets currently reserved
    - Assets already present in the NextTranscribableCampaignAsset table

    Args:
        campaign (Campaign): The campaign to filter assets by.

    Returns:
        QuerySet: Eligible assets ordered by sequence.
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


def find_next_transcribable_campaign_assets(campaign):
    """
    Returns all cached transcribable assets for a campaign.

    This accesses the NextTranscribableCampaignAsset cache table for the given campaign.

    Args:
        campaign (Campaign): The campaign to retrieve cached assets for.

    Returns:
        QuerySet: Cached assets
    """

    return concordia_models.NextTranscribableCampaignAsset.objects.filter(
        campaign=campaign
    )


@transaction.atomic
def find_transcribable_campaign_asset(campaign):
    """
    Retrieves a single transcribable asset from the campaign.

    Attempts to retrieve an asset from the cache table (NextTranscribableCampaignAsset).
    If no eligible asset is found, falls back to computing one directly from the
    Asset table and asynchronously schedules a background task to repopulate the cache.

    Ensures database row-level locking to prevent multiple concurrent consumers
    from selecting the same asset.

    Args:
        campaign (Campaign): The campaign to retrieve an asset from.

    Returns:
        Asset or None: A locked asset eligible for transcription, or None if
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
    campaign, project_slug, item_id, asset_pk
):
    """
    Retrieves and prioritizes cached transcribable assets based on proximity and status.

    Orders results from NextTranscribableCampaignAsset by (in this order):
    - Whether the asset is in the NOT_STARTED state
    - Whether the asset belongs to the same project
    - Whether the asset belongs to the same item
    - Then by sequence and id for stability

    Args:
        campaign (Campaign): The campaign to filter assets by.
        project_slug (str): Slug of the original asset's project.
        item_id (str): Item ID of the original asset.
        asset_pk (int): Primary key of the original asset (not used to order first).

    Returns:
        QuerySet: Prioritized list of candidate assets.
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
    campaign, project_slug, item_id, original_asset_id
):
    """
    Retrieves the next best transcribable asset for a user within a campaign.

    Priority for short-circuit selection (before cache/fallback):
    1) If item_id is provided, return the next NOT_STARTED asset in that item
       by sequence (> the original asset's sequence when available).
    2) If project_slug is provided, return the first NOT_STARTED asset in that
       project (ordered by item_id, then sequence). This step will not return the
       original asset and will avoid the current item to keep moving forward.

    If none of the above match, falls back to the cache-backed path:

    Attempts to retrieve an asset from the cache table
    (NextTranscribableCampaignAsset). If no eligible asset is found, falls back to
    computing one directly from the Asset table and asynchronously schedules a
    background task to repopulate the cache.

    After exhausting NOT_STARTED options, select the next IN_PROGRESS asset in the
    same item (by sequence > original when available).

    Ensures database row-level locking to prevent multiple concurrent consumers
    from selecting the same asset.

    Args:
        campaign (Campaign): The campaign to find an asset in.
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
            campaign_id=campaign.id,
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

    # Short-circuit: same project and NOT_STARTED
    # (avoid current item and original asset)
    if project_slug:
        candidate = concordia_models.Asset.objects.filter(
            campaign_id=campaign.id,
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

    # Cache-backed selection (NOT_STARTED anywhere), then manual fallback
    # (also NOT_STARTED)
    potential_next_assets = find_and_order_potential_transcribable_campaign_assets(
        campaign, project_slug, item_id, original_asset_id
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
            campaign=campaign,
        )
        spawn_task = True
        asset_query = find_new_transcribable_campaign_assets(campaign)
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


def find_invalid_next_transcribable_campaign_assets(campaign_id):
    """
    Returns NextTranscribableCampaignAsset objects that are no longer valid for
    transcription.

    Assets are considered invalid if:
    - Their transcription_status is not NOT_STARTED or IN_PROGRESS
    - They are currently reserved via AssetTranscriptionReservation

    This function is typically used to clean up the cached next-transcribable table,
    ensuring only eligible and available assets are retained.

    Args:
        campaign_id (int): ID of the campaign to filter assets by.

    Returns:
        QuerySet: Distinct set of invalid NextTranscribableCampaignAsset objects.
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
