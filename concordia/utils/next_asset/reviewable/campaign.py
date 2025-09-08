from django.db import transaction
from django.db.models import Case, IntegerField, Subquery, When

from concordia import models as concordia_models
from concordia.logging import ConcordiaLogger
from concordia.utils.celery import get_registered_task

structured_logger = ConcordiaLogger.get_logger(__name__)


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
def find_next_reviewable_campaign_asset(
    campaign, user, project_slug, item_id, original_asset_id
):
    """
    Retrieves the next best reviewable asset for a user within a campaign.

    Prioritizes assets from the cache that are:
    - After the current asset in sequence
    - In the same project or item

    Falls back to computing candidates if the cache is empty, and triggers
    a background task to repopulate the cache after selection.

    Args:
        campaign (Campaign): The campaign to find an asset in.
        user (User): The user requesting the asset.
        project_slug (str): Slug of the project the user is currently reviewing.
        item_id (str): ID of the item the user is currently reviewing.
        original_asset_id (int): ID of the asset the user just reviewed.

    Returns:
        Asset or None: A locked asset eligible for review, or None if unavailable.
    """

    potential_next_assets = find_and_order_potential_reviewable_campaign_assets(
        campaign, user, project_slug, item_id, original_asset_id
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
        # Spawn a task to populate the table for this campaign
        # We wait to do this until after getting an asset because otherwise there's a
        # a chance all valid assets get grabbed by the task and our query will return
        # nothing
        structured_logger.debug(
            "Spawned background task to populate cache",
            event_code="reviewable_next_cache_population",
            campaign=campaign,
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
