from typing import Dict

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Case, IntegerField, Q, QuerySet, Subquery, Value, When

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
        campaign (concordia_models.Campaign): Campaign whose reserved
        assets should be excluded.

    Returns:
        QuerySet[Dict[str, int]]: A queryset of dictionaries with a single key
            "asset_id" corresponding to reserved assets.
    """
    return concordia_models.AssetTranscriptionReservation.objects.filter(
        asset__campaign=campaign
    ).values("asset_id")


def _eligible_reviewable_base_qs(
    campaign: concordia_models.Campaign,
    user: User | None = None,
) -> "QuerySet[concordia_models.Asset]":
    """
    Build the base queryset of reviewable assets for a campaign.

    Behavior:
        Restricts to published projects, items, and assets, and to assets whose
        transcription status is `SUBMITTED`. Optionally excludes assets
        transcribed by the supplied user.

    Args:
        campaign (concordia_models.Campaign): Campaign scope for filtering.
        user (User | None): If provided, exclude assets transcribed by this user.

    Returns:
        QuerySet[concordia_models.Asset]: Reviewable assets, with `item` and
            `item__project` selected via `select_related`.
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


@transaction.atomic
def _find_reviewable_in_item(
    campaign: concordia_models.Campaign,
    user: User,
    *,
    item_id: str,
    after_asset_pk: int | None,
) -> "concordia_models.Asset | None":
    """
    Select the next reviewable asset within the same item.

    Behavior:
        Attempts a short-circuit within the user's current item to provide a
        locally contiguous review flow.

    Eligibility:
        - Asset, Item, and Project are published.
        - Asset transcription status is SUBMITTED.
        - Asset is not reserved.
        - Asset was not transcribed by the current user.

    Ordering:
        - If `after_asset_pk` refers to an asset in the same item and campaign,
          select the earliest asset whose (sequence, id) is strictly greater
          than the current asset's pair.
        - Otherwise, select the earliest eligible by (sequence, id).

    Args:
        campaign (concordia_models.Campaign): Campaign scope.
        user (User): Current user; used to exclude their own work.
        item_id (str): Identifier of the item to stay within.
        after_asset_pk (int | None): Asset primary key to advance from.

    Returns:
        concordia_models.Asset | None: A locked eligible asset, or
            None if no match is available.
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
    campaign: concordia_models.Campaign,
    user: User,
    *,
    project_slug: str,
    after_asset_pk: int | None,
) -> "concordia_models.Asset | None":
    """
    Select the first eligible reviewable asset within the same project.

    Behavior:
        Short-circuit when staying within a project. Sequence is per item,
        so this returns the first eligible asset, not strictly "after" a given asset.

    Eligibility:
        - Same campaign and project.
        - Asset, Item, and Project are published.
        - Asset transcription status is SUBMITTED.
        - Asset is not reserved.
        - Asset was not transcribed by the current user.

    Ordering:
        Deterministic by (item__item_id, sequence, id).

    Args:
        campaign (concordia_models.Campaign): Campaign scope.
        user (User): Current user; used to exclude their own work.
        project_slug (str): Slug of the project to stay within.
        after_asset_pk (int | None): Present for parity with the item
            variant; not used for ordering here.

    Returns:
        concordia_models.Asset | None: A locked eligible asset, or
            None if no match is available.
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


def find_new_reviewable_campaign_assets(
    campaign: concordia_models.Campaign,
    user: User | None = None,
) -> "QuerySet[concordia_models.Asset]":
    """
    Return assets in a campaign that are eligible to be added to the cache.

    Behavior:
        Builds the candidate set for the NextReviewableCampaignAsset cache by
        excluding assets that are not SUBMITTED, assets already reserved, and
        assets already present in the cache. Optionally excludes assets
        transcribed by the provided user.

    Args:
        campaign (concordia_models.Campaign): Campaign to filter by.
        user (User | None): If provided, exclude assets transcribed by this user.

    Returns:
        QuerySet[concordia_models.Asset]: Eligible assets ordered by sequence.
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


def find_next_reviewable_campaign_assets(
    campaign: concordia_models.Campaign,
    user: User,
) -> "QuerySet[concordia_models.NextReviewableCampaignAsset]":
    """
    Return cached reviewable assets in a campaign not transcribed by the user.

    Behavior:
        Reads from the NextReviewableCampaignAsset cache table and filters out
        assets where the requesting user appears in transcriber_ids.

    Args:
        campaign (concordia_models.Campaign): Campaign to retrieve cached assets from.
        user (User): Requesting user.

    Returns:
        QuerySet[concordia_models.NextReviewableCampaignAsset]: Cached candidate rows
        for the given user.
    """
    return concordia_models.NextReviewableCampaignAsset.objects.filter(
        campaign=campaign
    ).exclude(transcriber_ids__contains=[user.id])


@transaction.atomic
def find_reviewable_campaign_asset(
    campaign: concordia_models.Campaign,
    user: User,
) -> "concordia_models.Asset | None":
    """
    Retrieve a single reviewable asset for a user from a campaign.

    Behavior:
        First attempts to select a cached asset from NextReviewableCampaignAsset.
        If none is available, falls back to a direct query over Asset and
        triggers a background task to replenish the cache.

    Concurrency:
        Uses `select_for_update(skip_locked=True, of=("self",))` so only the
        Asset row is locked and concurrent consumers skip locked rows.

    Args:
        campaign (concordia_models.Campaign): Campaign to search within.
        user (User): Requesting user; their own transcriptions are excluded.

    Returns:
        concordia_models.Asset | None: A locked eligible asset, or None if unavailable.
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
    campaign: concordia_models.Campaign,
    user: User,
    project_slug: str,
    item_id: str,
    asset_pk: int | None,
) -> "QuerySet[concordia_models.NextReviewableCampaignAsset]":
    """
    Retrieve and prioritize cached reviewable assets for proximity.

    Behavior:
        Orders cached candidates from NextReviewableCampaignAsset to prefer
        continuity with the user's current location.

    Annotations added to each row (transient fields):
        - next_asset (int): 1 if the candidate's asset_id is greater than
            asset_pk, else 0.
        - same_project (int): 1 if the candidate shares the given
            project_slug, else 0.
        - same_item (int): 1 if the candidate shares the given item_id, else 0.

    Prioritization (descending on the following keys, then ascending by sequence):
        - next_asset
        - same_project
        - same_item
        - sequence

    Args:
        campaign (concordia_models.Campaign): Campaign to filter by.
        user (User): Requesting user.
        project_slug (str): Slug of the user's current project.
        item_id (str): Identifier of the user's current item.
        asset_pk (int | None): Identifier of the current asset, if any.

    Returns:
        QuerySet[concordia_models.NextReviewableCampaignAsset]: Prioritized
            cached candidates.
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
    campaign: concordia_models.Campaign,
    user: User,
    project_slug: str,
    item_id: str,
    original_asset_id: int | None,
) -> "concordia_models.Asset | None":
    """
    Retrieve the next best reviewable asset for a user within a campaign.

    Strategy:
        1. If `item_id` is provided, try a same-item short-circuit that advances
           by (sequence, id) relative to `original_asset_id`.
        2. Else, if `project_slug` is provided, select the first eligible asset
           within that project (short-circuit).
        3. Else, prioritize cached candidates, and if none are suitable, fall
           back to computing from Asset and trigger cache population.

    Concurrency:
        Uses `select_for_update(skip_locked=True, of=("self",))` to avoid
        double-assignments across concurrent consumers.

    Args:
        campaign (concordia_models.Campaign): Campaign to search within.
        user (User): Requesting user.
        project_slug (str): Slug of the user's current project.
        item_id (str): Identifier of the user's current item.
        original_asset_id (int | None): Identifier of the asset just reviewed.

    Returns:
        concordia_models.Asset | None: A locked eligible asset, or None if unavailable.
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


def find_invalid_next_reviewable_campaign_assets(
    campaign_id: int,
) -> "QuerySet[concordia_models.NextReviewableCampaignAsset]":
    """
    Return cache rows that are invalid for review for a given campaign.

    Behavior:
        Identifies NextReviewableCampaignAsset rows that are no longer valid
        because the underlying asset is not SUBMITTED or because the asset is
        currently reserved.

    Args:
        campaign_id (int): Identifier of the campaign.

    Returns:
        QuerySet[concordia_models.NextReviewableCampaignAsset]: Distinct
            invalid cache rows.
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
