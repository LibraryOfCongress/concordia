from logging import getLogger

from concordia.decorators import locked_task
from concordia.logging import ConcordiaLogger
from concordia.models import (
    Campaign,
    NextTranscribableCampaignAsset,
    NextTranscribableTopicAsset,
    Topic,
)
from concordia.utils.next_asset import (
    find_invalid_next_transcribable_campaign_assets,
    find_invalid_next_transcribable_topic_assets,
    find_new_transcribable_campaign_assets,
    find_new_transcribable_topic_assets,
)

from ...celery import app as celery_app

logger = getLogger(__name__)
structured_logger = ConcordiaLogger.get_logger(__name__)


@celery_app.task(bind=True, ignore_result=True)
@locked_task
def populate_next_transcribable_for_campaign(self, campaign_id):
    """
    Populate the cache of next transcribable assets for a campaign.

    This task checks how many transcribable assets are still needed for the
    campaign, finds eligible assets and inserts them into the
    NextTranscribableCampaignAsset table up to the target count.

    Only a single instance of the task runs at a time for a particular
    campaign_id by using the cache locking system to avoid duplication. This
    can be overridden with the `force` kwarg, which is stripped out by the
    decorator and not passed to the task itself. See the `locked_task`
    documentation for more information.

    Args:
        campaign_id: Primary key of the campaign to process.
    """
    try:
        campaign = Campaign.objects.get(id=campaign_id)
    except Campaign.DoesNotExist:
        logger.error("Campaign %s not found", campaign_id)
        return

    needed_asset_count = NextTranscribableCampaignAsset.objects.needed_for_campaign(
        campaign_id
    )
    if needed_asset_count:
        assets_qs = find_new_transcribable_campaign_assets(campaign).only(
            "id",
            "item_id",
            "item__project_id",
            "item__project__slug",
            "campaign_id",
            "transcription_status",
        )
        assets = assets_qs[:needed_asset_count]
    else:
        logger.info(
            "Campaign %s already has %s next transcribable assets",
            campaign,
            NextTranscribableCampaignAsset.objects.target_count,
        )
        return

    if assets:
        objs = NextTranscribableCampaignAsset.objects.bulk_create(
            [
                NextTranscribableCampaignAsset(
                    asset_id=asset.id,
                    item_id=asset.item_id,
                    item_item_id=asset.item.item_id,
                    project_id=asset.item.project_id,
                    project_slug=asset.item.project.slug,
                    campaign_id=asset.campaign_id,
                    transcription_status=asset.transcription_status,
                    sequence=asset.sequence,
                )
                for asset in assets
            ]
        )
        logger.info(
            "Added %d next transcribable assets for campaign %s", len(objs), campaign
        )
    else:
        logger.info("No transcribable assets found in campaign %s", campaign)


@celery_app.task(bind=True, ignore_result=True)
@locked_task
def populate_next_transcribable_for_topic(self, topic_id):
    """
    Populate the cache of next transcribable assets for a topic.

    This task checks how many transcribable assets are still needed for the
    topic, finds eligible assets and inserts them into the
    NextTranscribableTopicAsset table up to the target count.

    Only a single instance of the task runs at a time for a particular topic_id
    by using the cache locking system to avoid duplication. This can be
    overridden with the `force` kwarg, which is stripped out by the decorator
    and not passed to the task itself. See the `locked_task` documentation for
    more information.

    Args:
        topic_id: Primary key of the topic to process.
    """
    try:
        topic = Topic.objects.get(id=topic_id)
    except Topic.DoesNotExist:
        logger.error("Topic %s not found", topic_id)
        return

    needed_asset_count = NextTranscribableTopicAsset.objects.needed_for_topic(topic_id)
    if needed_asset_count:
        assets_qs = find_new_transcribable_topic_assets(topic).only(
            "id",
            "item_id",
            "item__project_id",
            "item__project__slug",
            "transcription_status",
        )
        assets = assets_qs[:needed_asset_count]
    else:
        logger.info(
            "Topic %s already has %s next transcribable assets",
            topic,
            NextTranscribableTopicAsset.objects.target_count,
        )
        return

    if assets:
        objs = NextTranscribableTopicAsset.objects.bulk_create(
            [
                NextTranscribableTopicAsset(
                    asset_id=asset.id,
                    item_id=asset.item_id,
                    item_item_id=asset.item.item_id,
                    project_id=asset.item.project_id,
                    project_slug=asset.item.project.slug,
                    topic_id=topic.id,
                    transcription_status=asset.transcription_status,
                    sequence=asset.sequence,
                )
                for asset in assets
            ]
        )
        logger.info("Added %d next transcribable assets for topic %s", len(objs), topic)
    else:
        logger.info("No transcribable assets found in topic %s", topic)


@celery_app.task(bind=True, ignore_result=True)
@locked_task
def clean_next_transcribable_for_campaign(self, campaign_id):
    """
    Remove invalid cached transcribable assets for a campaign then repopulate
    the cache.

    Invalid assets include those that are reserved or no longer eligible for
    transcription based on their transcription status. After cleaning, the
    corresponding populate task is queued to restore the cache to the target
    count.

    Args:
        campaign_id: Primary key of the campaign to clean.
    """

    for next_asset in find_invalid_next_transcribable_campaign_assets(campaign_id):
        try:
            next_asset.delete()
        except Exception:
            logger.exception("Error deleting cached asset %s", next_asset.id)
    logger.info(
        "Spawning populate_next_transcribable_for_campaign for campgin %s", campaign_id
    )
    populate_next_transcribable_for_campaign.delay(campaign_id)


@celery_app.task(bind=True, ignore_result=True)
@locked_task
def clean_next_transcribable_for_topic(self, topic_id):
    """
    Remove invalid cached transcribable assets for a topic then repopulate the
    cache.

    Invalid assets include those that are reserved or no longer eligible for
    transcription based on their transcription status. After cleaning, the
    corresponding populate task is queued to restore the cache to the target
    count.

    Args:
        topic_id: Primary key of the topic to clean.
    """

    for next_asset in find_invalid_next_transcribable_topic_assets(topic_id):
        try:
            next_asset.delete()
        except Exception:
            logger.exception("Error deleting cached asset %s", next_asset.id)
    logger.info("Spawning populate_next_transcribable_for_topic for topic %s", topic_id)
    populate_next_transcribable_for_topic.delay(topic_id)
