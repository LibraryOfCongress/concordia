from logging import getLogger

from concordia.decorators import locked_task
from concordia.logging import ConcordiaLogger
from concordia.models import Campaign, Topic

from ...celery import app as celery_app
from .reviewable import (
    clean_next_reviewable_for_campaign,
    clean_next_reviewable_for_topic,
)
from .transcribable import (
    clean_next_transcribable_for_campaign,
    clean_next_transcribable_for_topic,
)

logger = getLogger(__name__)
structured_logger = ConcordiaLogger.get_logger(__name__)


@celery_app.task(bind=True, ignore_result=True)
@locked_task
def renew_next_asset_cache(self):
    """
    Triggers cache cleaning and repopulation for all active campaigns and published
    topics.

    This runs cleaning tasks for both transcribable and reviewable assets across all
    campaigns and topics. Each cleaning task ensures that the next asset cache remains
    accurate and up to date by removing invalid entries and restoring the desired count.
    """

    for campaign in Campaign.objects.active():
        logger.info("Spawning clean_next_transcribable_for_campaign for %s", campaign)
        clean_next_transcribable_for_campaign.delay(campaign_id=campaign.id)
        logger.info("Spawning clean_next_reviewable_for_campaign for %s", campaign)
        clean_next_reviewable_for_campaign.delay(campaign_id=campaign.id)

    for topic in Topic.objects.published():
        logger.info("Spawning clean_next_transcribable_for_topic for %s", topic)
        clean_next_transcribable_for_topic.delay(topic_id=topic.id)
        logger.info("Spawning clean_next_reviewable_for_topic for %s", topic)
        clean_next_reviewable_for_topic.delay(topic_id=topic.id)
