from itertools import chain
from logging import getLogger

from concordia.decorators import locked_task
from concordia.logging import ConcordiaLogger
from concordia.models import (
    Campaign,
    NextReviewableCampaignAsset,
    NextReviewableTopicAsset,
    Topic,
)
from concordia.utils import get_anonymous_user
from concordia.utils.next_asset import (
    find_invalid_next_reviewable_campaign_assets,
    find_invalid_next_reviewable_topic_assets,
    find_new_reviewable_campaign_assets,
    find_new_reviewable_topic_assets,
)

from ...celery import app as celery_app

logger = getLogger(__name__)
structured_logger = ConcordiaLogger.get_logger(__name__)


@celery_app.task(bind=True, ignore_result=True)
@locked_task
def populate_next_reviewable_for_campaign(self, campaign_id):
    """
    Populate the next reviewable cache for a campaign.

    This task checks how many reviewable assets are still needed for the
    campaign, finds eligible assets and inserts them into the
    NextReviewableCampaignAsset table up to the target count.

    The task prefers assets whose transcribers are not already represented in
    the cache to avoid review bottlenecks.

    Only a single instance of this task runs at a time for a given campaign,
    using the cache locking system to avoid duplication. This can be
    overridden with the ``force`` keyword argument, which is stripped by the
    decorator and not passed to the task itself. See the ``locked_task``
    documentation for details.

    Args:
        campaign_id: Primary key of the campaign to process.
    """
    try:
        campaign = Campaign.objects.get(id=campaign_id)
    except Campaign.DoesNotExist:
        logger.error("Campaign %s not found", campaign_id)
        return
    anonymous_user = get_anonymous_user()
    excluded_user_ids = (
        NextReviewableCampaignAsset.objects.filter(campaign=campaign)
        .exclude(transcriber_ids__contains=[anonymous_user.id])
        .values_list("transcriber_ids", flat=True)
        .distinct()
    )
    # Flatten the list and deduplicate
    excluded_user_ids = set(chain.from_iterable(excluded_user_ids))

    needed_asset_count = NextReviewableCampaignAsset.objects.needed_for_campaign(
        campaign_id
    )
    if needed_asset_count:
        assets_qs = find_new_reviewable_campaign_assets(campaign).only(
            "id",
            "item_id",
            "item__project_id",
            "item__project__slug",
            "campaign_id",
            "transcription__user",
        )
        # We prefer to not use transcribers that already exist, to avoid
        # the situation where all possible reviewable assets have the same
        # transcriber (since that would mean that user would miss the cache
        # table when they try to review).
        # If that's impossible, we just take whatever assets we can; that means
        # only these transcribers have reviewable assets in the campaign
        excluded_assets_qs = assets_qs.exclude(
            transcription__user_id__in=excluded_user_ids
        )
        if excluded_assets_qs.exists():
            assets_qs = excluded_assets_qs
        assets = assets_qs[:needed_asset_count]
    else:
        logger.info(
            "Campaign %s already has %s next reviewable assets",
            campaign,
            NextReviewableCampaignAsset.objects.target_count,
        )
        return

    if assets:
        objs = NextReviewableCampaignAsset.objects.bulk_create(
            [
                NextReviewableCampaignAsset(
                    asset_id=asset.id,
                    item_id=asset.item_id,
                    item_item_id=asset.item.item_id,
                    project_id=asset.item.project_id,
                    project_slug=asset.item.project.slug,
                    campaign_id=asset.campaign_id,
                    transcriber_ids=list(
                        asset.transcription_set.exclude(user=anonymous_user)
                        .values_list("user_id", flat=True)
                        .distinct()
                    ),
                    sequence=asset.sequence,
                )
                for asset in assets
            ]
        )
        logger.info(
            "Added %d next reviewable assets for campaign %s", len(objs), campaign
        )
    else:
        logger.info("No reviewable assets found in campaign %s", campaign)


@celery_app.task(bind=True, ignore_result=True)
@locked_task
def populate_next_reviewable_for_topic(self, topic_id):
    """
    Populate the next reviewable cache for a topic.

    This task checks how many reviewable assets are still needed for the topic,
    finds eligible assets and inserts them into the NextReviewableTopicAsset
    table up to the target count.

    The task prefers assets whose transcribers are not already represented in
    the cache to avoid review bottlenecks.

    Only a single instance of this task runs at a time for a given topic,
    using the cache locking system to avoid duplication. This can be
    overridden with the ``force`` keyword argument, which is stripped by the
    decorator and not passed to the task itself. See the ``locked_task``
    documentation for details.

    Args:
        topic_id: Primary key of the topic to process.
    """
    try:
        topic = Topic.objects.get(id=topic_id)
    except Topic.DoesNotExist:
        logger.error("Topic %s not found", topic_id)
        return
    anonymous_user = get_anonymous_user()
    excluded_user_ids = (
        NextReviewableTopicAsset.objects.filter(topic=topic)
        .exclude(transcriber_ids__contains=[anonymous_user.id])
        .values_list("transcriber_ids", flat=True)
        .distinct()
    )
    # Flatten the list and deduplicate
    excluded_user_ids = set(chain.from_iterable(excluded_user_ids))

    needed_asset_count = NextReviewableTopicAsset.objects.needed_for_topic(topic_id)
    if needed_asset_count:
        assets_qs = find_new_reviewable_topic_assets(topic).only(
            "id",
            "item_id",
            "item__project_id",
            "item__project__slug",
            "transcription__user",
        )
        # We prefer to not use transcribers that already exist, to avoid
        # the situation where all possible reviewable assets have the same
        # transcriber (since that would mean that user would miss the cache
        # table when they try to review).
        # If that's impossible, we just take whatever assets we can; that means
        # only these transcribers have reviewable assets in the campaign
        excluded_assets_qs = assets_qs.exclude(
            transcription__user_id__in=excluded_user_ids
        )
        if excluded_assets_qs.exists():
            assets_qs = excluded_assets_qs
        assets = assets_qs[:needed_asset_count]
    else:
        logger.info(
            "Topic %s already has %s next reviewable assets",
            topic,
            NextReviewableTopicAsset.objects.target_count,
        )
        return

    if assets:
        objs = NextReviewableTopicAsset.objects.bulk_create(
            [
                NextReviewableTopicAsset(
                    asset_id=asset.id,
                    item_id=asset.item_id,
                    item_item_id=asset.item.item_id,
                    project_id=asset.item.project_id,
                    project_slug=asset.item.project.slug,
                    topic_id=topic.id,
                    transcriber_ids=list(
                        asset.transcription_set.exclude(user=anonymous_user)
                        .values_list("user_id", flat=True)
                        .distinct()
                    ),
                    sequence=asset.sequence,
                )
                for asset in assets
            ]
        )
        logger.info("Added %d next reviewable assets for topic %s", len(objs), topic)
    else:
        logger.info("No reviewable assets found in topic %s", topic)


@celery_app.task(bind=True, ignore_result=True)
@locked_task
def clean_next_reviewable_for_campaign(self, campaign_id):
    """
    Clean cached reviewable assets for a campaign then repopulate the cache.

    Invalid entries are those whose assets no longer have transcription status
    ``SUBMITTED`` and are no longer eligible for review. After cleaning, the
    corresponding populate task is queued to restore the cache to the target
    count.

    Args:
        campaign_id: Primary key of the campaign to clean.
    """

    for next_asset in find_invalid_next_reviewable_campaign_assets(campaign_id):
        try:
            next_asset.delete()
        except Exception:
            logger.exception("Error deleting cached asset %s", next_asset.id)
    logger.info(
        "Spawning populate_next_reviewable_for_campaign for campgin %s", campaign_id
    )
    populate_next_reviewable_for_campaign.delay(campaign_id)


@celery_app.task(bind=True, ignore_result=True)
@locked_task
def clean_next_reviewable_for_topic(self, topic_id):
    """
    Clean cached reviewable assets for a topic then repopulate the cache.

    Invalid entries are those whose assets no longer have transcription status
    ``SUBMITTED`` and are no longer eligible for review. After cleaning, the
    corresponding populate task is queued to restore the cache to the target
    count.

    Args:
        topic_id: Primary key of the topic to clean.
    """

    for next_asset in find_invalid_next_reviewable_topic_assets(topic_id):
        try:
            next_asset.delete()
        except Exception:
            logger.exception("Error deleting cached asset %s", next_asset.id)
    logger.info("Spawning populate_next_reviewable_for_topic for topic %s", topic_id)
    populate_next_reviewable_for_topic.delay(topic_id)
