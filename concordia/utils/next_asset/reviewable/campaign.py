from django.db import transaction
from django.db.models import Case, IntegerField, Q, Subquery, Value, When

from concordia import models as concordia_models
from concordia.logging import ConcordiaLogger
from concordia.utils.celery import get_registered_task

structured_logger = ConcordiaLogger.get_logger(__name__)


def _reserved_asset_ids_subq(campaign):
    """
    Subquery of reserved asset IDs for the given campaign. Used to exclude
    assets that currently have an active reservation.
    """
    return concordia_models.AssetTranscriptionReservation.objects.filter(
        asset__campaign=campaign
    ).values("asset_id")


def _eligible_reviewable_base_qs(campaign, user=None):
    """
    Base queryset for reviewable assets within a campaign, restricted to
    published objects and SUBMITTED status. Optionally excludes assets
    transcribed by the given user.
    """
    qs = concordia_models.Asset.objects.filter(
        campaign_id=campaign.id,
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
    Resolve the sequence number for the given asset primary key. Returns None
    if the PK is falsy or if no corresponding asset exists.
    """
    if not pk:
        return None
    return (
        concordia_models.Asset.objects.filter(pk=pk)
        .values_list("sequence", flat=True)
        .first()
    )


@transaction.atomic
def _find_reviewable_in_item(
    campaign, user, *, item_id: str, after_asset_pk: int | None
):
    """
    Short-circuit helper: return the next reviewable asset within the same item
    for the given campaign and user.

    Ordering rule:
        - Advance within the item by (sequence, id) strictly greater than the
          current asset, if an original asset is provided and belongs to the same
          item/campaign.
        - Otherwise return the earliest eligible by (sequence, id).

    Eligibility:
        - Asset.published = True, Item.published = True, Project.published = True
        - transcription_status == SUBMITTED
        - Not reserved in AssetTranscriptionReservation
        - Exclude assets transcribed by `user`

    Args:
        campaign (Campaign): Campaign scope.
        user (User): Requesting user (to exclude their own work).
        item_id (str): Item.item_id to stay within.
        after_asset_pk (int | None): The pk of the asset we are advancing from.

    Returns:
        Asset | None: Locked eligible asset, or None if no match.
    """
    reserved_asset_ids = concordia_models.AssetTranscriptionReservation.objects.filter(
        asset__item__item_id=item_id,
        asset__item__project__campaign=campaign,
    ).values("asset_id")

    eligible = (
        concordia_models.Asset.objects.filter(
            item__item_id=item_id,
            item__project__campaign=campaign,
            item__project__published=True,
            item__published=True,
            published=True,
            transcription_status=concordia_models.TranscriptionStatus.SUBMITTED,
        )
        .exclude(pk__in=Subquery(reserved_asset_ids))
        .exclude(transcription__user=user.id)
    )

    seq_gt_filter = None
    if after_asset_pk is not None:
        try:
            current = (
                concordia_models.Asset.objects.only("id", "sequence", "item_id", "item")
                .select_related("item")
                .get(pk=after_asset_pk)
            )
            if (
                current.item.item_id == item_id
                and current.item.project.campaign_id == campaign.id
            ):
                seq_gt_filter = Q(sequence__gt=current.sequence) | (
                    Q(sequence=current.sequence) & Q(id__gt=after_asset_pk)
                )
        except concordia_models.Asset.DoesNotExist:
            pass

    if seq_gt_filter is not None:
        eligible = eligible.filter(seq_gt_filter)

    asset = (
        eligible.select_for_update(skip_locked=True, of=("self",))
        .select_related("item", "item__project")
        .order_by("sequence", "id")
        .first()
    )

    structured_logger.debug(
        "Item short-circuit (campaign reviewable) resolved.",
        event_code="reviewable_item_short_circuit_campaign",
        campaign=campaign,
        item_id=item_id,
        after_asset_pk=after_asset_pk,
        chosen_asset_id=getattr(asset, "id", None),
    )
    return asset


@transaction.atomic
def _find_reviewable_in_project(
    campaign, user, *, project_slug: str, after_asset_pk: int | None
):
    """
    Short-circuit helper: return the first eligible reviewable asset within the same
    project for the given campaign and user.

    Notes:
        - This is a *first eligible* selector, not an "after current" selector,
          since sequence is per-item. We keep the result deterministic by ordering
          by (item__item_id, sequence, id).

    Eligibility:
        - Same campaign & project
        - Asset/Item/Project published
        - transcription_status == SUBMITTED
        - Not reserved; exclude assets transcribed by `user`

    Returns:
        Asset | None
    """
    reserved_asset_ids = concordia_models.AssetTranscriptionReservation.objects.filter(
        asset__item__project__slug=project_slug,
        asset__item__project__campaign=campaign,
    ).values("asset_id")

    eligible = (
        concordia_models.Asset.objects.filter(
            item__project__campaign=campaign,
            item__project__slug=project_slug,
            item__project__published=True,
            item__published=True,
            published=True,
            transcription_status=concordia_models.TranscriptionStatus.SUBMITTED,
        )
        .exclude(pk__in=Subquery(reserved_asset_ids))
        .exclude(transcription__user=user.id)
        .select_for_update(skip_locked=True, of=("self",))
        .select_related("item", "item__project")
        .order_by("item__item_id", "sequence", "id")
        .first()
    )

    structured_logger.debug(
        "Project short-circuit (campaign reviewable) resolved.",
        event_code="reviewable_project_short_circuit_campaign",
        campaign=campaign,
        project_slug=project_slug,
        after_asset_pk=after_asset_pk,
        chosen_asset_id=getattr(eligible, "id", None),
    )
    return eligible


def find_new_reviewable_campaign_assets(campaign, user=None):
    """
    Returns a queryset of assets in the given campaign that are eligible for review
    caching.

    This excludes:
    - Assets with transcription_status not SUBMITTED
    - Assets currently reserved
    - Assets already present in the NextReviewableCampaignAsset table
    - Optionally, assets transcribed by the given user

    Args:
        campaign (Campaign): The campaign to filter assets by.
        user (User, optional): If provided, assets transcribed by this user will be
        excluded.

    Returns:
        QuerySet: Eligible assets ordered by sequence.
    """

    reserved_asset_ids = concordia_models.AssetTranscriptionReservation.objects.filter(
        asset__campaign=campaign
    ).values("asset_id")
    next_asset_ids = concordia_models.NextReviewableCampaignAsset.objects.filter(
        campaign=campaign
    ).values("asset_id")

    queryset = (
        concordia_models.Asset.objects.filter(
            campaign_id=campaign.id,
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


def find_next_reviewable_campaign_assets(campaign, user):
    """
    Returns cached reviewable assets for a campaign that were not transcribed by the
    given user.

    This accesses the NextReviewableCampaignAsset cache table and filters out any
    assets associated with the given user via the transcriber_ids field.

    Args:
        campaign (Campaign): The campaign to filter assets by.
        user (User): The user requesting a reviewable asset.

    Returns:
        QuerySet: Cached assets
    """

    return concordia_models.NextReviewableCampaignAsset.objects.filter(
        campaign=campaign
    ).exclude(transcriber_ids__contains=[user.id])


@transaction.atomic
def find_reviewable_campaign_asset(campaign, user):
    """
    Retrieves a single reviewable asset from the campaign for the given user.

    Attempts to retrieve an asset from the cache table (NextReviewableCampaignAsset).
    If no eligible asset is found, falls back to computing one directly from the
    Asset table and asynchronously schedules a background task to repopulate the cache.

    Ensures database row-level locking to prevent multiple concurrent consumers
    from selecting the same asset.

    Args:
        campaign (Campaign): The campaign to retrieve an asset from.
        user (User): The user requesting the asset (used to exclude their own work).

    Returns:
        Asset or None: A locked asset eligible for review, or None if unavailable.
    """

    next_asset = (
        find_next_reviewable_campaign_assets(campaign, user)
        .select_for_update(skip_locked=True, of=("self",))
        .values_list("asset_id", flat=True)
        .first()
    )

    spawn_task = False
    if next_asset:
        asset_query = concordia_models.Asset.objects.filter(id=next_asset)
    else:
        # No asset in the NextReviewableCampaignAsset table for this campaign
        # and user, so fallback to manually finding one
        structured_logger.debug(
            "No cached assets available, falling back to manual lookup",
            event_code="reviewable_fallback_manual_lookup",
            campaign=campaign,
            user=user,
        )
        spawn_task = True
        asset_query = find_new_reviewable_campaign_assets(campaign, user)

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
            event_code="reviewable_cache_population_triggered",
            campaign=campaign,
            user=user,
        )
        populate_task = get_registered_task(
            "concordia.tasks.populate_next_reviewable_for_campaign"
        )
        populate_task.delay(campaign.id)
    return asset


def find_and_order_potential_reviewable_campaign_assets(
    campaign, user, project_slug, item_id, asset_pk
):
    """
    Retrieves and prioritizes cached reviewable assets for a user based on proximity.

    Orders results from NextReviewableCampaignAsset by:
    - Whether the asset comes after the given asset in sequence
    - Whether the asset belongs to the same project
    - Whether the asset belongs to the same item

    Args:
        campaign (Campaign): The campaign to filter assets by.
        user (User): The user requesting the next asset.
        project_slug (str): Slug of the original asset's project.
        item_id (str): Item ID of the original asset.
        asset_pk (int): Primary key of the original asset.

    Returns:
        QuerySet: Prioritized list of candidate assets.
    """

    potential_next_assets = find_next_reviewable_campaign_assets(campaign, user)

    # We'll favor assets which are in the same item or project as the original:
    next_case = (
        Case(
            When(asset_id__gt=asset_pk, then=1),
            default=0,
            output_field=IntegerField(),
        )
        if asset_pk is not None
        else Value(0, output_field=IntegerField())
    )

    potential_next_assets = potential_next_assets.annotate(
        same_project=Case(
            When(project_slug=project_slug, then=1),
            default=0,
            output_field=IntegerField(),
        ),
        same_item=Case(
            When(item_item_id=item_id, then=1), default=0, output_field=IntegerField()
        ),
        next_asset=next_case,
    ).order_by("-next_asset", "-same_project", "-same_item", "sequence")

    return potential_next_assets


@transaction.atomic
def find_next_reviewable_campaign_asset(
    campaign, user, project_slug, item_id, original_asset_id
):
    """
    Retrieves the next best reviewable asset for a user within a campaign.

    - If item_id is provided, first try to return the next eligible asset
      in that item by sequence (short-circuit).
    - Else if project_slug is provided, try to return the first eligible
      asset within that project (short-circuit).
    - Else fall back to the existing cache-backed path:

    Attempts to retrieve an asset from the cache table (NextReviewableCampaignAsset).
    If no eligible asset is found, falls back to computing one directly from the
    Asset table and asynchronously schedules a background task to repopulate the cache.

    Ensures database row-level locking to prevent multiple concurrent consumers
    from selecting the same asset.

    Args:
        campaign (Campaign): The campaign to find an asset in.
        user (User): The user requesting the asset.
        project_slug (str): Slug of the project the user is currently reviewing.
        item_id (str): ID of the item the user is currently reviewing.
        original_asset_id (int): ID of the asset the user just reviewed.

    Returns:
        Asset or None: A locked asset eligible for review, or None if
        unavailable.
    """
    try:
        after_pk = int(original_asset_id) if original_asset_id else None
    except (TypeError, ValueError):
        after_pk = None

    # Short-circuit: same item
    if item_id:
        asset = _find_reviewable_in_item(
            campaign, user, item_id=item_id, after_asset_pk=after_pk
        )
        if asset:
            return asset

    # Short-circuit: same project
    if project_slug:
        asset = _find_reviewable_in_project(
            campaign, user, project_slug=project_slug, after_asset_pk=after_pk
        )
        if asset:
            return asset

    # cache-backed selection, then manual fallback
    potential_next_assets = find_and_order_potential_reviewable_campaign_assets(
        campaign, user, project_slug, item_id, after_pk
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
            campaign=campaign,
            user=user,
        )
        spawn_task = True
        asset_query = find_new_reviewable_campaign_assets(campaign, user)

        next_case = (
            Case(
                When(id__gt=after_pk, then=1),
                default=0,
                output_field=IntegerField(),
            )
            if after_pk is not None
            else Value(0, output_field=IntegerField())
        )

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
            next_asset=next_case,
        ).order_by("-next_asset", "-same_project", "-same_item", "sequence")

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
            event_code="reviewable_next_cache_population",
            campaign=campaign,
            user=user,
        )
        populate_task = get_registered_task(
            "concordia.tasks.populate_next_reviewable_for_campaign"
        )
        populate_task.delay(campaign.id)

    return asset


def find_invalid_next_reviewable_campaign_assets(campaign_id):
    """
    Returns a queryset of NextReviewableCampaignAsset records that are no longer valid
    for review. This includes:
    - Assets with a transcription status other than SUBMITTED.
    - Assets currently reserved via AssetTranscriptionReservation.

    Args:
        campaign_id (int): The ID of the campaign to filter by.

    Returns:
        QuerySet: Invalid NextReviewableCampaignAsset records.
    """
    reserved_asset_ids = concordia_models.AssetTranscriptionReservation.objects.filter(
        asset__campaign_id=campaign_id
    ).values("asset_id")

    status_filtered = concordia_models.NextReviewableCampaignAsset.objects.exclude(
        asset__transcription_status=concordia_models.TranscriptionStatus.SUBMITTED
    ).filter(campaign_id=campaign_id)

    reserved_filtered = concordia_models.NextReviewableCampaignAsset.objects.filter(
        campaign_id=campaign_id, asset_id__in=Subquery(reserved_asset_ids)
    )

    return (status_filtered | reserved_filtered).distinct()
