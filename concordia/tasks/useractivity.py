from logging import getLogger
from typing import Iterable

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.mail import send_mail
from django.db.models import Q

from concordia.decorators import locked_task
from concordia.exceptions import CacheLockedError
from concordia.logging import ConcordiaLogger
from concordia.models import (
    Asset,
    Campaign,
    Tag,
    Transcription,
    UserAssetTagCollection,
    UserProfileActivity,
    _update_useractivity_cache,
    update_userprofileactivity_table,
)
from concordia.utils import get_anonymous_user

from ..celery import app as celery_app

logger = getLogger(__name__)
structured_logger = ConcordiaLogger.get_logger(__name__)


def _populate_activity_table(campaigns: Iterable[Campaign]) -> None:
    """
    Populate UserProfileActivity rows for the given campaigns.

    For each campaign this helper calculates per user counts of assets,
    tags, transcriptions and reviews and bulk creates rows for all
    non-anonymous users. It also updates or creates an aggregate row for
    the anonymous user.

    Args:
        campaigns: Iterable of Campaign instances to process.
    """
    anonymous_user = get_anonymous_user()
    for campaign in campaigns:
        transcriptions = Transcription.objects.filter(
            asset__item__project__campaign=campaign
        )
        reviewer_ids = (
            transcriptions.exclude(reviewed_by=anonymous_user)
            .values_list("reviewed_by", flat=True)
            .distinct()
        )
        transcriber_ids = (
            transcriptions.exclude(user=anonymous_user)
            .values_list("user", flat=True)
            .distinct()
        )
        user_ids = list(set(list(reviewer_ids) + list(transcriber_ids)))
        tag_collections = UserAssetTagCollection.objects.filter(
            asset__item__project__campaign=campaign
        )
        UserProfileActivity.objects.bulk_create(
            [
                UserProfileActivity(
                    user=user,
                    campaign=campaign,
                    asset_count=Asset.objects.filter(item__project__campaign=campaign)
                    .filter(
                        Q(transcription__reviewed_by=user) | Q(transcription__user=user)
                    )
                    .distinct()
                    .count(),
                    asset_tag_count=Tag.objects.filter(
                        userassettagcollection__in=tag_collections.filter(user=user)
                    )
                    .distinct()
                    .count(),
                    transcribe_count=transcriptions.filter(Q(user=user))
                    .distinct()
                    .count(),
                    review_count=transcriptions.filter(Q(reviewed_by=user))
                    .distinct()
                    .count(),
                )
                for user in User.objects.filter(id__in=user_ids)
            ]
        )
        assets = Asset.objects.filter(item__project__campaign=campaign)
        q = Q(transcription__reviewed_by=anonymous_user) | Q(
            transcription__user=anonymous_user
        )
        user_profile_activity, _ = UserProfileActivity.objects.get_or_create(
            user=anonymous_user,
            campaign=campaign,
        )
        user_profile_activity.asset_count = assets.filter(q).distinct().count()
        user_profile_activity.asset_tag_count = (
            Tag.objects.filter(
                userassettagcollection__in=tag_collections.filter(user=anonymous_user)
            )
            .distinct()
            .count()
        )
        user_profile_activity.transcribe_count = (
            transcriptions.filter(Q(user=anonymous_user)).distinct().count()
        )
        user_profile_activity.review_count = (
            transcriptions.filter(Q(reviewed_by=anonymous_user)).distinct().count()
        )
        user_profile_activity.save()


@celery_app.task
def populate_completed_campaign_counts() -> None:
    """
    Populate UserProfileActivity for completed and retired campaigns.

    This task should be run after the UserProfileActivity table is
    created. It processes all campaigns that are not active by
    delegating to ``_populate_activity_table``.
    """
    # this task creates records in the UserProfileActivity table for campaigns
    # that are completed or have status == RETIRED (but have not yet actually
    # been retired). It should be run once, after the table has initially been
    # created
    # in my local env, this task took ~10 minutes to complete
    campaigns = Campaign.objects.exclude(status=Campaign.Status.ACTIVE)
    _populate_activity_table(campaigns)


@celery_app.task
def populate_active_campaign_counts() -> None:
    """
    Populate UserProfileActivity for active campaigns.

    This task builds or refreshes activity rows for campaigns whose
    status is ACTIVE by delegating to ``_populate_activity_table``.
    """
    active_campaigns = Campaign.objects.filter(status=Campaign.Status.ACTIVE)
    _populate_activity_table(active_campaigns)


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=5,
    retry_kwargs={"max_retries": 5, "countdown": 5},
)
def update_useractivity_cache(
    self,
    user_id: int,
    campaign_id: int,
    attr_name: str,
    *args,
    **kwargs,
) -> None:
    """
    Update cached user activity counts for a single metric.

    This Celery task acquires a short lived cache based lock to prevent
    concurrent updates for the same key. On success it calls
    ``_update_useractivity_cache`` then releases the lock and logs a
    completion event. If the lock cannot be acquired after the retry
    budget it logs a warning and sends an email to the developer list.

    Args:
        user_id: Primary key of the user to update.
        campaign_id: Primary key of the campaign whose cache is updated.
        attr_name: Name of the activity attribute being incremented,
            for example ``"transcribe_count"`` or ``"review_count"``.

    Raises:
        CacheLockedError: If the cache lock cannot be acquired before
            retries are exhausted.
    """
    structured_logger.info(
        "Running update_useractivity_cache task",
        event_code="useractivity_cache_task_start",
        user_id=user_id,
        campaign_id=campaign_id,
        activity_type=attr_name,
        attempt=self.request.retries + 1,
    )
    try:
        lock_key = "userprofileactivity_cache_lock"

        # attempt to acquire
        if not cache.add(lock_key, "locked", timeout=10):
            raise CacheLockedError(f"Could not acquire lock for {lock_key}")

        try:
            _update_useractivity_cache(user_id, campaign_id, attr_name)
            structured_logger.info(
                "Successfully updated user activity cache",
                event_code="useractivity_cache_task_complete",
                user_id=user_id,
                campaign_id=campaign_id,
                activity_type=attr_name,
            )
        finally:
            # release
            cache.delete(lock_key)

    except Exception as e:
        if self.request.retries >= self.max_retries:
            structured_logger.warning(
                "Could not acquire cache lock",
                event_code="useractivity_cache_lock_failed",
                reason="Another task is holding the lock",
                reason_code="lock_unavailable",
                user_id=user_id,
                campaign_id=campaign_id,
                activity_type=attr_name,
            )
            structured_logger.exception(
                "Failed to update user activity cache after retries.",
                event_code="useractivity_cache_task_failed",
                reason="Max retries reached while trying to acquire lock.",
                reason_code="max_retries_exceeded",
                user_id=user_id,
                campaign_id=campaign_id,
                activity_type=attr_name,
            )
            subject = "Task update_useractivity_cache failed: cache is locked."
            message_body = """%s
                            user: %s
                            campaign: %s
                            attribute: %s
                          """ % (
                e,
                user_id,
                campaign_id,
                attr_name,
            )
            logger.error("%s %s Retrying...", subject, message_body)
            send_mail(
                subject,
                message_body,
                settings.DEFAULT_FROM_EMAIL,
                settings.CONCORDIA_DEVS,
            )
        # Let celery handle retries
        raise e


@celery_app.task(bind=True, ignore_result=True)
@locked_task
def update_userprofileactivity_from_cache(self) -> None:
    """
    Flush per campaign activity deltas from cache to the database.

    This task is wrapped by the ``locked_task`` decorator so only one
    instance runs at a time. For each campaign it reads the cached
    update payload, writes transcribe and review counts with
    ``update_userprofileactivity_table`` then clears the cache entry.
    """
    structured_logger.info(
        "Starting update_userprofileactivity_from_cache task",
        event_code="starting_update_userprofileactivity_from_cache_task",
    )
    for campaign in Campaign.objects.all():
        key = f"userprofileactivity_{campaign.pk}"
        structured_logger.debug(
            "Read key",
            event_code="update_userprofileactivity_from_cache_key_read",
            key=key,
        )
        updates_by_user = cache.get(key)
        if updates_by_user is not None:
            cache.delete(key)
            for user_id in updates_by_user:
                user = User.objects.get(id=user_id)
                update_userprofileactivity_table(
                    user,
                    campaign.id,
                    "transcribe_count",
                    updates_by_user[user_id][0],
                )
                update_userprofileactivity_table(
                    user,
                    campaign.id,
                    "review_count",
                    updates_by_user[user_id][1],
                )
                structured_logger.debug(
                    "Updated activity counts for user",
                    event_code=("update_userprofileactivity_from_cache_database_write"),
                    user=user_id,
                )
        else:
            structured_logger.debug(
                "Cache contained no updates for key. Skipping",
                event_code="update_userprofileactivity_from_cache_no_updates",
                key=key,
            )
