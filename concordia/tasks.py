import csv
import datetime
import os.path
import time
from datetime import timedelta
from io import StringIO
from itertools import chain
from logging import getLogger
from tempfile import NamedTemporaryFile
from typing import Iterable, Optional

import boto3
import requests
from celery import chord, group
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core.cache import cache, caches
from django.core.files.base import ContentFile
from django.core.mail import EmailMultiAlternatives, send_mail
from django.core.management import call_command
from django.db import transaction
from django.db.models import Count, F, Max, Q
from django.template import loader
from django.utils import timezone
from more_itertools.more import chunked

from concordia.decorators import locked_task
from concordia.exceptions import CacheLockedError
from concordia.logging import ConcordiaLogger
from concordia.models import (
    ONE_DAY_AGO,
    Asset,
    AssetTranscriptionReservation,
    Campaign,
    CampaignRetirementProgress,
    Item,
    KeyMetricsReport,
    NextReviewableCampaignAsset,
    NextReviewableTopicAsset,
    NextTranscribableCampaignAsset,
    NextTranscribableTopicAsset,
    Project,
    ResourceFile,
    SiteReport,
    Tag,
    Topic,
    Transcription,
    TranscriptionStatus,
    UserAssetTagCollection,
    UserProfileActivity,
    _update_useractivity_cache,
    update_userprofileactivity_table,
)
from concordia.parser import extract_og_image, fetch_blog_posts
from concordia.signals.signals import reservation_released
from concordia.storage import ASSET_STORAGE, VISUALIZATION_STORAGE
from concordia.utils import get_anonymous_user
from concordia.utils.next_asset import (
    find_invalid_next_reviewable_campaign_assets,
    find_invalid_next_reviewable_topic_assets,
    find_invalid_next_transcribable_campaign_assets,
    find_invalid_next_transcribable_topic_assets,
    find_new_reviewable_campaign_assets,
    find_new_reviewable_topic_assets,
    find_new_transcribable_campaign_assets,
    find_new_transcribable_topic_assets,
)

from .celery import app as celery_app

logger = getLogger(__name__)
structured_logger = ConcordiaLogger.get_logger(__name__)

ENV_MAPPING = {"development": "DEV", "test": "TEST", "staging": "STAGE"}


@celery_app.task
def expire_inactive_asset_reservations():
    timestamp = timezone.now()

    # Clear old reservations, with a grace period:
    cutoff = timestamp - (
        datetime.timedelta(seconds=2 * settings.TRANSCRIPTION_RESERVATION_SECONDS)
    )

    logger.debug("Clearing reservations with last reserve time older than %s", cutoff)
    expired_reservations = AssetTranscriptionReservation.objects.filter(
        updated_on__lt=cutoff, tombstoned__in=(None, False)
    )

    for reservation in expired_reservations:
        logger.debug("Expired reservation with token %s", reservation.reservation_token)
        reservation_released.send(
            sender="reserve_asset",
            asset_pk=reservation.asset.pk,
            reservation_token=reservation.reservation_token,
        )
        reservation.delete()


@celery_app.task
def tombstone_old_active_asset_reservations():
    timestamp = timezone.now()

    cutoff = timestamp - (
        datetime.timedelta(hours=settings.TRANSCRIPTION_RESERVATION_TOMBSTONE_HOURS)
    )

    old_reservations = AssetTranscriptionReservation.objects.filter(
        created_on__lt=cutoff, tombstoned__in=(None, False)
    )
    for reservation in old_reservations:
        logger.debug("Tombstoning reservation %s ", reservation.reservation_token)
        reservation.tombstoned = True
        reservation.save()


@celery_app.task
def delete_old_tombstoned_reservations():
    timestamp = timezone.now()

    cutoff = timestamp - (
        datetime.timedelta(
            hours=settings.TRANSCRIPTION_RESERVATION_TOMBSTONE_LENGTH_HOURS
        )
    )

    old_reservations = AssetTranscriptionReservation.objects.filter(
        tombstoned__exact=True, updated_on__lt=cutoff
    )
    for reservation in old_reservations:
        logger.debug(
            "Deleting old tombstoned reservation %s", reservation.reservation_token
        )
        reservation.delete()


def _recent_transcriptions():
    qs = Transcription.objects.filter(
        Q(accepted__gte=ONE_DAY_AGO)
        | Q(created_on__gte=ONE_DAY_AGO)
        | Q(rejected__gte=ONE_DAY_AGO)
        | Q(submitted__gte=ONE_DAY_AGO)
        | Q(updated_on__gte=ONE_DAY_AGO)
    )
    structured_logger.info(
        "Fetched recent transcriptions for DAU calculation.",
        event_code="recent_transcriptions_fetched",
        transcription_count=qs.count(),
    )
    return qs


def _daily_active_users():
    transcriptions = _recent_transcriptions()
    transcriber_ids = transcriptions.values_list("user", flat=True).distinct()
    reviewer_ids = (
        transcriptions.exclude(reviewed_by__isnull=True)
        .values_list("reviewed_by", flat=True)
        .distinct()
    )
    transcriber_count = transcriber_ids.count()
    reviewer_count = reviewer_ids.count()
    daily_active_users = len(set(list(reviewer_ids) + list(transcriber_ids)))

    structured_logger.info(
        "Calculated daily active users from recent transcriptions.",
        event_code="daily_active_users_calculated",
        transcriber_count=transcriber_count,
        reviewer_count=reviewer_count,
        daily_active_users=daily_active_users,
    )
    return daily_active_users


@celery_app.task
def site_report():
    structured_logger.debug(
        "Starting site report generation task.",
        event_code="site_report_task_start",
    )
    report = {
        "assets_not_started": 0,
        "assets_in_progress": 0,
        "assets_submitted": 0,
        "assets_completed": 0,
    }

    asset_count_qs = Asset.objects.values_list("transcription_status").annotate(
        Count("transcription_status")
    )
    for status, count in asset_count_qs:
        logger.debug("Assets %s: %d", status, count)
        report[f"assets_{status}"] = count

    assets_total = Asset.objects.count()
    assets_published = Asset.objects.published().count()
    assets_unpublished = Asset.objects.unpublished().count()

    items_published = Item.objects.published().count()
    items_unpublished = Item.objects.unpublished().count()

    projects_published = Project.objects.published().count()
    projects_unpublished = Project.objects.unpublished().count()

    campaigns_published = Campaign.objects.published().count()
    campaigns_unpublished = Campaign.objects.unpublished().count()

    users_registered = User.objects.all().count()
    users_activated = User.objects.filter(is_active=True).count()

    anonymous_transcriptions = Transcription.objects.filter(
        user=get_anonymous_user()
    ).count()
    transcriptions_saved = Transcription.objects.all().count()

    daily_review_actions = Transcription.objects.recent_review_actions().count()

    stats = UserAssetTagCollection.objects.aggregate(Count("tags"))
    tag_count = stats["tags__count"]

    distinct_tag_count = Tag.objects.all().count()

    previous = SiteReport.objects.previous_in_series(
        report_name=SiteReport.ReportName.TOTAL, before=timezone.now()
    )
    assets_started = SiteReport.calculate_assets_started(
        previous_assets_not_started=getattr(previous, "assets_not_started", 0),
        previous_assets_published=getattr(previous, "assets_published", 0),
        current_assets_not_started=report["assets_not_started"],
        current_assets_published=assets_published,
    )

    site_report = SiteReport()
    site_report.report_name = SiteReport.ReportName.TOTAL
    site_report.assets_total = assets_total
    site_report.assets_published = assets_published
    site_report.assets_not_started = report["assets_not_started"]
    site_report.assets_in_progress = report["assets_in_progress"]
    site_report.assets_waiting_review = report["assets_submitted"]
    site_report.assets_completed = report["assets_completed"]
    site_report.assets_unpublished = assets_unpublished
    site_report.assets_started = assets_started
    site_report.items_published = items_published
    site_report.items_unpublished = items_unpublished
    site_report.projects_published = projects_published
    site_report.projects_unpublished = projects_unpublished
    site_report.anonymous_transcriptions = anonymous_transcriptions
    site_report.transcriptions_saved = transcriptions_saved
    site_report.daily_review_actions = daily_review_actions
    site_report.distinct_tags = distinct_tag_count
    site_report.tag_uses = tag_count
    site_report.campaigns_published = campaigns_published
    site_report.campaigns_unpublished = campaigns_unpublished
    site_report.users_registered = users_registered
    site_report.users_activated = users_activated
    site_report.daily_active_users = _daily_active_users()

    structured_logger.debug(
        "Site-wide counts calculated for report generation.",
        event_code="site_report_counts_calculated",
        assets_total=assets_total,
        assets_published=assets_published,
        assets_unpublished=assets_unpublished,
        assets_started=assets_started,
        items_published=items_published,
        items_unpublished=items_unpublished,
        projects_published=projects_published,
        projects_unpublished=projects_unpublished,
        campaigns_published=campaigns_published,
        campaigns_unpublished=campaigns_unpublished,
        users_registered=users_registered,
        users_activated=users_activated,
        anonymous_transcriptions=anonymous_transcriptions,
        transcriptions_saved=transcriptions_saved,
        daily_review_actions=daily_review_actions,
        distinct_tags=distinct_tag_count,
        tag_uses=tag_count,
        daily_active_users=site_report.daily_active_users,
    )

    site_report.save()

    structured_logger.debug(
        "Site-wide report saved successfully.",
        event_code="site_report_saved",
        site_report_id=site_report.id,
        created_on=site_report.created_on.isoformat(),
    )

    campaigns = Campaign.objects.exclude(status=Campaign.Status.RETIRED)
    structured_logger.debug(
        "Generating campaign reports.",
        event_code="campaign_reports_generation_start",
        campaign_count=campaigns.count(),
    )
    for campaign in campaigns:
        campaign_report(campaign)
    structured_logger.debug(
        "Campaign reports generation completed.",
        event_code="campaign_reports_generation_complete",
    )

    topics = Topic.objects.all()
    structured_logger.debug(
        "Generating topic reports.",
        event_code="topic_reports_generation_start",
        topic_count=topics.count(),
    )
    for topic in topics:
        topic_report(topic)
    structured_logger.debug(
        "Topic reports generation completed.",
        event_code="topic_reports_generation_complete",
    )

    retired_total_report()
    structured_logger.debug(
        "Retired total report generation completed.",
        event_code="retired_total_report_complete",
    )

    structured_logger.debug(
        "Site report generation task completed successfully.",
        event_code="site_report_task_complete",
    )


def topic_report(topic):
    structured_logger.debug(
        "Starting topic report generation.",
        event_code="topic_report_generation_start",
        topic_slug=topic,
    )
    report = {
        "assets_not_started": 0,
        "assets_in_progress": 0,
        "assets_submitted": 0,
        "assets_completed": 0,
    }

    asset_count_qs = (
        Asset.objects.filter(item__project__topics=topic)
        .values_list("transcription_status")
        .annotate(Count("transcription_status"))
    )

    for status, count in asset_count_qs:
        logger.debug("Topic %s assets %s: %d", topic.slug, status, count)
        report[f"assets_{status}"] = count

    assets_total = Asset.objects.filter(item__project__topics=topic).count()
    if assets_total == 0:
        structured_logger.warning(
            "Topic report generated with zero total assets.",
            event_code="topic_report_zero_assets",
            reason="Topic has no associated assets",
            reason_code="no_assets",
            topic=topic,
        )
    assets_published = (
        Asset.objects.published().filter(item__project__topics=topic).count()
    )
    assets_unpublished = (
        Asset.objects.unpublished().filter(item__project__topics=topic).count()
    )

    items_published = Item.objects.published().filter(project__topics=topic).count()
    items_unpublished = Item.objects.unpublished().filter(project__topics=topic).count()

    projects_published = Project.objects.published().filter(topics=topic).count()
    projects_unpublished = Project.objects.unpublished().filter(topics=topic).count()

    anonymous_transcriptions = Transcription.objects.filter(
        asset__item__project__topics=topic, user=get_anonymous_user()
    ).count()
    transcriptions_saved = Transcription.objects.filter(
        asset__item__project__topics=topic
    ).count()

    daily_review_actions = (
        Transcription.objects.recent_review_actions()
        .filter(asset__item__project__topics__in=(topic,))
        .count()
    )

    asset_tag_collections = UserAssetTagCollection.objects.filter(
        asset__item__project__topics=topic
    )

    stats = asset_tag_collections.order_by().aggregate(tag_count=Count("tags"))
    tag_count = stats["tag_count"]

    distinct_tag_list = set()

    for tag_collection in asset_tag_collections:
        distinct_tag_list.update(tag_collection.tags.values_list("pk", flat=True))

    distinct_tag_count = len(distinct_tag_list)

    previous = SiteReport.objects.previous_in_series(topic=topic, before=timezone.now())
    assets_started = SiteReport.calculate_assets_started(
        previous_assets_not_started=getattr(previous, "assets_not_started", 0),
        previous_assets_published=getattr(previous, "assets_published", 0),
        current_assets_not_started=report["assets_not_started"],
        current_assets_published=assets_published,
    )

    structured_logger.debug(
        "Topic counts calculated for report generation.",
        event_code="topic_report_counts_calculated",
        topic=topic,
        assets_total=assets_total,
        assets_published=assets_published,
        assets_unpublished=assets_unpublished,
        assets_started=assets_started,
        items_published=items_published,
        items_unpublished=items_unpublished,
        projects_published=projects_published,
        projects_unpublished=projects_unpublished,
        anonymous_transcriptions=anonymous_transcriptions,
        transcriptions_saved=transcriptions_saved,
        daily_review_actions=daily_review_actions,
        distinct_tags=distinct_tag_count,
        tag_uses=tag_count,
    )
    site_report = SiteReport()
    site_report.topic = topic
    site_report.assets_total = assets_total
    site_report.assets_published = assets_published
    site_report.assets_not_started = report["assets_not_started"]
    site_report.assets_in_progress = report["assets_in_progress"]
    site_report.assets_waiting_review = report["assets_submitted"]
    site_report.assets_completed = report["assets_completed"]
    site_report.assets_unpublished = assets_unpublished
    site_report.items_published = items_published
    site_report.items_unpublished = items_unpublished
    site_report.projects_published = projects_published
    site_report.projects_unpublished = projects_unpublished
    site_report.anonymous_transcriptions = anonymous_transcriptions
    site_report.transcriptions_saved = transcriptions_saved
    site_report.daily_review_actions = daily_review_actions
    site_report.distinct_tags = distinct_tag_count
    site_report.tag_uses = tag_count
    site_report.assets_started = assets_started
    site_report.save()
    structured_logger.debug(
        "Topic report saved successfully.",
        event_code="topic_report_saved",
        topic=topic,
        site_report_id=site_report.id,
        created_on=site_report.created_on.isoformat(),
    )


def campaign_report(campaign):
    structured_logger.debug(
        "Starting campaign report generation.",
        event_code="campaign_report_generation_start",
        campaign=campaign,
    )
    report = {
        "assets_not_started": 0,
        "assets_in_progress": 0,
        "assets_submitted": 0,
        "assets_completed": 0,
    }

    asset_count_qs = (
        Asset.objects.filter(item__project__campaign=campaign)
        .values_list("transcription_status")
        .annotate(Count("transcription_status"))
    )

    for status, count in asset_count_qs:
        logger.debug("Campaign %s assets %s: %d", campaign.slug, status, count)
        report[f"assets_{status}"] = count

    assets_total = Asset.objects.filter(item__project__campaign=campaign).count()
    if assets_total == 0:
        structured_logger.warning(
            "Campaign report generated with zero total assets.",
            event_code="campaign_report_zero_assets",
            reason="Campaign has no associated assets",
            reason_code="no_assets",
            campaign=campaign,
        )
    assets_published = (
        Asset.objects.published().filter(item__project__campaign=campaign).count()
    )
    assets_unpublished = (
        Asset.objects.unpublished().filter(item__project__campaign=campaign).count()
    )

    items_published = (
        Item.objects.published().filter(project__campaign=campaign).count()
    )
    items_unpublished = (
        Item.objects.unpublished().filter(project__campaign=campaign).count()
    )

    projects_published = Project.objects.published().filter(campaign=campaign).count()
    projects_unpublished = (
        Project.objects.unpublished().filter(campaign=campaign).count()
    )

    anonymous_transcriptions = Transcription.objects.filter(
        asset__item__project__campaign=campaign, user=get_anonymous_user()
    ).count()
    transcriptions_saved = Transcription.objects.filter(
        asset__item__project__campaign=campaign
    ).count()

    daily_review_actions = (
        Transcription.objects.recent_review_actions()
        .filter(asset__item__project__campaign=campaign)
        .count()
    )

    asset_tag_collections = UserAssetTagCollection.objects.filter(
        asset__item__project__campaign=campaign
    )

    stats = asset_tag_collections.order_by().aggregate(tag_count=Count("tags"))
    tag_count = stats["tag_count"]

    distinct_tag_list = set()

    for tag_collection in asset_tag_collections:
        distinct_tag_list.update(tag_collection.tags.values_list("pk", flat=True))

    distinct_tag_count = len(distinct_tag_list)

    campaign_assets = Asset.objects.filter(
        item__project__campaign=campaign,
        item__project__published=True,
        item__published=True,
        published=True,
    )
    asset_transcriptions = Transcription.objects.filter(
        asset__in=campaign_assets
    ).values_list("user_id", "reviewed_by")
    user_ids = {
        user_id
        for transcription in asset_transcriptions
        for user_id in transcription
        if user_id
    }
    registered_contributor_count = len(user_ids)

    previous = SiteReport.objects.previous_in_series(
        campaign=campaign, before=timezone.now()
    )
    assets_started = SiteReport.calculate_assets_started(
        previous_assets_not_started=getattr(previous, "assets_not_started", 0),
        previous_assets_published=getattr(previous, "assets_published", 0),
        current_assets_not_started=report["assets_not_started"],
        current_assets_published=assets_published,
    )

    structured_logger.debug(
        "Campaign counts calculated for report generation.",
        event_code="campaign_report_counts_calculated",
        campaign=campaign,
        assets_total=assets_total,
        assets_published=assets_published,
        assets_unpublished=assets_unpublished,
        assets_started=assets_started,
        items_published=items_published,
        items_unpublished=items_unpublished,
        projects_published=projects_published,
        projects_unpublished=projects_unpublished,
        anonymous_transcriptions=anonymous_transcriptions,
        transcriptions_saved=transcriptions_saved,
        daily_review_actions=daily_review_actions,
        distinct_tags=distinct_tag_count,
        tag_uses=tag_count,
        registered_contributors=registered_contributor_count,
    )
    site_report = SiteReport()
    site_report.campaign = campaign
    site_report.assets_total = assets_total
    site_report.assets_published = assets_published
    site_report.assets_not_started = report["assets_not_started"]
    site_report.assets_in_progress = report["assets_in_progress"]
    site_report.assets_waiting_review = report["assets_submitted"]
    site_report.assets_completed = report["assets_completed"]
    site_report.assets_unpublished = assets_unpublished
    site_report.items_published = items_published
    site_report.items_unpublished = items_unpublished
    site_report.projects_published = projects_published
    site_report.projects_unpublished = projects_unpublished
    site_report.anonymous_transcriptions = anonymous_transcriptions
    site_report.transcriptions_saved = transcriptions_saved
    site_report.daily_review_actions = daily_review_actions
    site_report.distinct_tags = distinct_tag_count
    site_report.tag_uses = tag_count
    site_report.registered_contributors = registered_contributor_count
    site_report.assets_started = assets_started
    site_report.save()
    structured_logger.debug(
        "Campaign report saved successfully.",
        event_code="campaign_report_saved",
        campaign=campaign,
        site_report_id=site_report.id,
        created_on=site_report.created_on.isoformat(),
    )


def retired_total_report():
    structured_logger.debug(
        "Starting retired total report generation.",
        event_code="retired_total_report_generation_start",
    )
    site_reports = (
        SiteReport.objects.filter(campaign__status=Campaign.Status.RETIRED)
        .order_by("campaign_id", "-created_on")
        .distinct("campaign_id")
    )
    site_report_count = site_reports.count()
    structured_logger.debug(
        "Fetched site reports for retired campaigns aggregation.",
        event_code="retired_total_reports_fetched",
        report_count=site_report_count,
    )

    FIELDS = [
        "assets_total",
        "assets_published",
        "assets_not_started",
        "assets_in_progress",
        "assets_waiting_review",
        "assets_completed",
        "assets_unpublished",
        "items_published",
        "items_unpublished",
        "projects_published",
        "projects_unpublished",
        "anonymous_transcriptions",
        "transcriptions_saved",
        "daily_review_actions",
        "distinct_tags",
        "tag_uses",
        "registered_contributors",
    ]
    total_site_report = SiteReport()
    total_site_report.report_name = SiteReport.ReportName.RETIRED_TOTAL
    # You can't use aggregate with distinct(*fields), so the sum for each
    # has to be done in Python
    for field in FIELDS:
        setattr(
            total_site_report,
            field,
            sum(
                [
                    getattr(site_report, field) if getattr(site_report, field) else 0
                    for site_report in site_reports
                ]
            ),
        )

    # compute assets_started for RETIRED_TOTAL based on prior retired-total reports
    # This is done different than the fields above because it isn't simply a sum of
    # the component reports.
    previous = SiteReport.objects.previous_in_series(
        report_name=SiteReport.ReportName.RETIRED_TOTAL, before=timezone.now()
    )
    assets_started = SiteReport.calculate_assets_started(
        previous_assets_not_started=getattr(previous, "assets_not_started", 0),
        previous_assets_published=getattr(previous, "assets_published", 0),
        current_assets_not_started=total_site_report.assets_not_started,
        current_assets_published=total_site_report.assets_published,
    )

    total_site_report.assets_started = assets_started
    total_site_report.save()
    structured_logger.debug(
        "Retired total report saved successfully.",
        event_code="retired_total_report_saved",
        site_report_id=total_site_report.id,
        created_on=total_site_report.created_on.isoformat(),
    )


@celery_app.task(bind=True, ignore_result=True)
@locked_task(lock_by_args=False)
def backfill_assets_started_for_site_reports(self, skip_existing: bool = True) -> int:
    """
    Compute and persist `assets_started` for all existing SiteReport rows.

    This is a temporary job for backfilling missing information in SiteReports.
    It should be removed in the next release after it goes live and has been run.

    Series processed:
      - Site-wide TOTAL                (report_name=TOTAL)
      - Site-wide RETIRED_TOTAL        (report_name=RETIRED_TOTAL)
      - Per-campaign                   (campaign is not null)
      - Per-topic                      (topic is not null)

    Rules:
      - The first "snapshot" in each series assumes assets_started = 0 (this
        represents when the site launched or at least the time before the
        first site report, when we have no data).
      - If there are gaps in days, the previous value is simply the most
        recent prior report in that series.
      - All results are floored at 0, since negative numbers are not actually
        possible in reality—the cause would be data removal, which we do not
        want to treat as negative activity in these reports.

    Resumability:
      - By default, rows that already have a non-null `assets_started` are
        skipped (`skip_existing=True`), so the task can be re-run to resume
        where it left off.
      - If you need to recompute all rows (for example, after changing the
        formula), call with `skip_existing=False`.

    Progress visibility:
      - Emits heartbeat logs while scanning long series so it does not appear
        idle when no rows need updates.
    """

    structured_logger.info(
        "Starting backfill for assets_started across all series.",
        event_code="assets_started_backfill_start",
        skip_existing=skip_existing,
        task_id=getattr(self.request, "id", None),
    )

    # Heartbeat / streaming tuning
    HEARTBEAT_EVERY_ROWS = 1000
    HEARTBEAT_EVERY_SECONDS = 10.0
    ITERATOR_CHUNK_SIZE = 2000

    updated_count = 0

    def process_series_queryset(
        qs: Iterable[SiteReport],
        *,
        series_label: str,
    ) -> int:
        """
        Walk a single series in chronological order, computing/saving
        `assets_started`. Logs each saved row at info level with context,
        and emits heartbeat logs even when no rows change.
        """
        changed = 0
        scanned = 0
        previous: Optional[SiteReport] = None

        series_start_t = time.monotonic()
        last_hb_t = series_start_t
        last_hb_rows = 0

        structured_logger.info(
            "Starting series scan.",
            event_code="assets_started_backfill_series_start",
            series=series_label,
        )

        for current in qs.iterator(chunk_size=ITERATOR_CHUNK_SIZE):
            scanned += 1

            if previous is None:
                calculated = 0
            else:
                calculated = SiteReport.calculate_assets_started(
                    previous_assets_not_started=previous.assets_not_started,
                    previous_assets_published=previous.assets_published,
                    current_assets_not_started=current.assets_not_started,
                    current_assets_published=current.assets_published,
                )

            # Resume behavior: optionally skip already-populated rows.
            if skip_existing and current.assets_started is not None:
                previous = current
                # Heartbeat while scanning even if we do not save
                now_t = time.monotonic()
                if (
                    scanned - last_hb_rows >= HEARTBEAT_EVERY_ROWS
                    or (now_t - last_hb_t) >= HEARTBEAT_EVERY_SECONDS
                ):
                    structured_logger.info(
                        "Scanning series...",
                        event_code="assets_started_backfill_series_heartbeat",
                        series=series_label,
                        scanned_rows=scanned,
                        updated_rows=changed,
                        last_seen_site_report_id=current.id,
                    )
                    last_hb_rows = scanned
                    last_hb_t = now_t
                continue

            if current.assets_started != calculated:
                current.assets_started = calculated
                current.save(update_fields=["assets_started"])
                changed += 1

                # Per-row progress log for monitoring while the one-off task runs.
                structured_logger.info(
                    "Backfilled assets_started for SiteReport.",
                    event_code="assets_started_backfill_row",
                    site_report_id=current.id,
                    created_on=current.created_on.isoformat(),
                    series=series_label,
                    assets_started=calculated,
                    previous_site_report_id=(previous.id if previous else None),
                    campaign_id=current.campaign_id,
                    topic_id=current.topic_id,
                )

            previous = current

            # Heartbeat while scanning
            now_t = time.monotonic()
            if (
                scanned - last_hb_rows >= HEARTBEAT_EVERY_ROWS
                or (now_t - last_hb_t) >= HEARTBEAT_EVERY_SECONDS
            ):
                structured_logger.info(
                    "Scanning series...",
                    event_code="assets_started_backfill_series_heartbeat",
                    series=series_label,
                    scanned_rows=scanned,
                    updated_rows=changed,
                    last_seen_site_report_id=current.id,
                )
                last_hb_rows = scanned
                last_hb_t = now_t

        structured_logger.info(
            "Finished series scan.",
            event_code="assets_started_backfill_series_done",
            series=series_label,
            scanned_rows=scanned,
            updated_rows=changed,
            elapsed_seconds=round(time.monotonic() - series_start_t, 3),
        )
        return changed

    # Site-wide TOTAL
    if SiteReport.objects.filter(
        report_name=SiteReport.ReportName.TOTAL,
        campaign__isnull=True,
        topic__isnull=True,
        assets_started__isnull=True,
    ).exists():
        total_qs = SiteReport.objects.filter(
            report_name=SiteReport.ReportName.TOTAL,
            campaign__isnull=True,
            topic__isnull=True,
        ).order_by("created_on", "pk")
        updated_count += process_series_queryset(total_qs, series_label="TOTAL")

    # Site-wide RETIRED_TOTAL
    if SiteReport.objects.filter(
        report_name=SiteReport.ReportName.RETIRED_TOTAL,
        assets_started__isnull=True,
    ).exists():
        retired_total_qs = SiteReport.objects.filter(
            report_name=SiteReport.ReportName.RETIRED_TOTAL
        ).order_by("created_on", "pk")
        updated_count += process_series_queryset(
            retired_total_qs, series_label="RETIRED_TOTAL"
        )

    # Per-campaign (includes retired campaigns; their historical reports remain)
    campaign_ids = (
        SiteReport.objects.filter(campaign__isnull=False, assets_started__isnull=True)
        .values_list("campaign_id", flat=True)
        .distinct()
    )
    for campaign_id in campaign_ids.iterator():
        campaign_series = SiteReport.objects.filter(campaign_id=campaign_id).order_by(
            "created_on", "pk"
        )
        updated_count += process_series_queryset(
            campaign_series, series_label=f"CAMPAIGN:{campaign_id}"
        )

    # Per-topic
    topic_ids = (
        SiteReport.objects.filter(topic__isnull=False, assets_started__isnull=True)
        .values_list("topic_id", flat=True)
        .distinct()
    )
    for topic_id in topic_ids.iterator():
        topic_series = SiteReport.objects.filter(topic_id=topic_id).order_by(
            "created_on", "pk"
        )
        updated_count += process_series_queryset(
            topic_series, series_label=f"TOPIC:{topic_id}"
        )

    structured_logger.info(
        "Completed backfill for assets_started.",
        event_code="assets_started_backfill_complete",
        updated_rows=updated_count,
        task_id=getattr(self.request, "id", None),
    )
    return updated_count


@celery_app.task(bind=True, ignore_result=True)
@locked_task(lock_by_args=False)
def build_key_metrics_reports(self, recompute_all: bool = False) -> int:
    """
    Build or refresh KeyMetricsReport rows (monthly, quarterly, fiscal year).

    Modes:
      - recompute_all=True:
          * Recompute EVERY monthly period that is computable from SiteReport.
          * Then recompute ALL quarters that have at least one monthly row.
          * Then recompute ALL fiscal years that have at least one quarterly row.
      - recompute_all=False (default, incremental):
          * Create any MISSING monthly rows.
          * Refresh any EXISTING monthly row if any SiteReport in that month has
            created_on > monthly.updated_on (keeps partial months current).
          * Create any MISSING quarter rows that have at least one monthly row.
          * Refresh any EXISTING quarter whose input monthly rows have
            updated_on > quarter.updated_on.
          * Create any MISSING fiscal year rows that have at least one quarter row.
          * Refresh any EXISTING fiscal year whose input quarter rows have
            updated_on > fiscal_year.updated_on.

    Returns:
        int: Count of KeyMetricsReport rows created or updated.
    """
    task_id = getattr(self.request, "id", None)
    structured_logger.info(
        "Starting KeyMetricsReport build.",
        event_code="key_metrics_build_start",
        task_id=task_id,
        recompute_all=recompute_all,
    )

    rows_changed = 0

    # Determine month range we can evaluate
    earliest_site_report = SiteReport.objects.order_by("created_on", "pk").first()
    earliest_date = earliest_site_report.created_on.date()
    first_month_start = earliest_date.replace(day=1)

    # Use local date for boundary logic
    today_local = timezone.localdate()
    # Evaluate up to the month containing "yesterday"
    # so we never rely on future EOM snapshots
    yesterday_local = today_local - datetime.timedelta(days=1)
    _, latest_evaluated_end_of_month = KeyMetricsReport.month_bounds(yesterday_local)

    def has_any_snapshot_by_end_of_month(month_start: datetime.date) -> bool:
        _, end_of_month = KeyMetricsReport.month_bounds(month_start)
        return SiteReport.objects.filter(created_on__date__lte=end_of_month).exists()

    last_month_start = latest_evaluated_end_of_month.replace(day=1)
    # Step back if the very latest month has no SiteReport by its EOM
    while (
        last_month_start >= first_month_start
        and not has_any_snapshot_by_end_of_month(last_month_start)
    ):
        if last_month_start.month == 1:
            last_month_start = last_month_start.replace(
                year=last_month_start.year - 1, month=12, day=1
            )
        else:
            last_month_start = last_month_start.replace(
                month=last_month_start.month - 1, day=1
            )

    if last_month_start < first_month_start:
        structured_logger.info(
            "No computable monthly periods found.",
            event_code="key_metrics_build_no_months",
            task_id=task_id,
        )
        return 0

    # Monthly

    months_processed: list[datetime.date] = []
    current_month_start = first_month_start
    while current_month_start <= last_month_start:
        year = current_month_start.year
        month = current_month_start.month
        _, current_month_end = KeyMetricsReport.month_bounds(current_month_start)

        if recompute_all:
            report = KeyMetricsReport.upsert_month(year=year, month=month)
            if report is not None:
                rows_changed += 1
                months_processed.append(current_month_start)
                structured_logger.info(
                    "Upserted monthly KeyMetricsReport.",
                    event_code="key_metrics_month_upserted",
                    year=year,
                    month=month,
                    period_start=str(report.period_start),
                    period_end=str(report.period_end),
                    task_id=task_id,
                )
        else:
            # Incremental mode: create missing, or refresh if stale
            existing_monthly_report = KeyMetricsReport.objects.filter(
                period_type=KeyMetricsReport.PeriodType.MONTHLY,
                fiscal_year=KeyMetricsReport.get_fiscal_year_for_date(
                    current_month_start
                ),
                month=month,
            ).first()

            if existing_monthly_report is None:
                report = KeyMetricsReport.upsert_month(year=year, month=month)
                if report is not None:
                    rows_changed += 1
                    months_processed.append(current_month_start)
                    structured_logger.info(
                        "Created missing monthly KeyMetricsReport.",
                        event_code="key_metrics_month_created",
                        year=year,
                        month=month,
                        period_start=str(report.period_start),
                        period_end=str(report.period_end),
                        task_id=task_id,
                    )
            else:
                # Refresh if any SiteReport within this month (TOTAL
                # or RETIRED_TOTAL, site-wide) has been created after
                # the monthly report was last updated.
                site_report_newer_exists = SiteReport.objects.filter(
                    report_name__in=(
                        SiteReport.ReportName.TOTAL,
                        SiteReport.ReportName.RETIRED_TOTAL,
                    ),
                    campaign__isnull=True,
                    topic__isnull=True,
                    created_on__date__gte=current_month_start,
                    created_on__date__lte=current_month_end,
                    created_on__gt=existing_monthly_report.updated_on,
                ).exists()

                if site_report_newer_exists:
                    report = KeyMetricsReport.upsert_month(year=year, month=month)
                    if report is not None:
                        rows_changed += 1
                        months_processed.append(current_month_start)
                        structured_logger.info(
                            (
                                "Refreshed monthly KeyMetricsReport "
                                "due to newer SiteReports."
                            ),
                            event_code="key_metrics_month_refreshed",
                            year=year,
                            month=month,
                            period_start=str(report.period_start),
                            period_end=str(report.period_end),
                            task_id=task_id,
                        )

        # Next month
        if month == 12:
            current_month_start = current_month_start.replace(
                year=year + 1, month=1, day=1
            )
        else:
            current_month_start = current_month_start.replace(month=month + 1, day=1)

    # Quarterly

    # Ensure we know which quarters exist (or should exist) given MONTHLY rows
    monthly_rows = (
        KeyMetricsReport.objects.filter(period_type=KeyMetricsReport.PeriodType.MONTHLY)
        .values("fiscal_year")
        .annotate(max_month=Max("month"))
    )
    # We will iterate over all fiscal_years that have at least one monthly row
    fiscal_years_with_monthlies = {row["fiscal_year"] for row in monthly_rows}

    # Create missing quarters and refresh stale ones
    for fiscal_year in sorted(fiscal_years_with_monthlies):
        for fiscal_quarter in (1, 2, 3, 4):
            quarter_exists = KeyMetricsReport.objects.filter(
                period_type=KeyMetricsReport.PeriodType.QUARTERLY,
                fiscal_year=fiscal_year,
                fiscal_quarter=fiscal_quarter,
            ).first()

            if recompute_all:
                quarter_report = KeyMetricsReport.upsert_quarter(
                    fiscal_year=fiscal_year, fiscal_quarter=fiscal_quarter
                )
                if quarter_report is not None:
                    rows_changed += 1
                    structured_logger.info(
                        "Upserted quarterly KeyMetricsReport.",
                        event_code="key_metrics_quarter_upserted",
                        fiscal_year=fiscal_year,
                        fiscal_quarter=fiscal_quarter,
                        period_start=str(quarter_report.period_start),
                        period_end=str(quarter_report.period_end),
                        task_id=task_id,
                    )
                continue

            # Incremental mode
            if quarter_exists is None:
                quarter_report = KeyMetricsReport.upsert_quarter(
                    fiscal_year=fiscal_year, fiscal_quarter=fiscal_quarter
                )
                if quarter_report is not None:
                    rows_changed += 1
                    structured_logger.info(
                        "Created missing quarterly KeyMetricsReport.",
                        event_code="key_metrics_quarter_created",
                        fiscal_year=fiscal_year,
                        fiscal_quarter=fiscal_quarter,
                        period_start=str(quarter_report.period_start),
                        period_end=str(quarter_report.period_end),
                        task_id=task_id,
                    )
            else:
                # Refresh if any constituent MONTHLY rows are newer than the quarter row
                if fiscal_quarter == 1:
                    month_list = [10, 11, 12]
                    monthly_fiscal_year = fiscal_year
                elif fiscal_quarter == 2:
                    month_list = [1, 2, 3]
                    monthly_fiscal_year = fiscal_year
                elif fiscal_quarter == 3:
                    month_list = [4, 5, 6]
                    monthly_fiscal_year = fiscal_year
                else:
                    month_list = [7, 8, 9]
                    monthly_fiscal_year = fiscal_year

                monthly_newer_exists = KeyMetricsReport.objects.filter(
                    period_type=KeyMetricsReport.PeriodType.MONTHLY,
                    fiscal_year=monthly_fiscal_year,
                    month__in=month_list,
                    updated_on__gt=quarter_exists.updated_on,
                ).exists()

                if monthly_newer_exists:
                    quarter_report = KeyMetricsReport.upsert_quarter(
                        fiscal_year=fiscal_year, fiscal_quarter=fiscal_quarter
                    )
                    if quarter_report is not None:
                        rows_changed += 1
                        structured_logger.info(
                            (
                                "Refreshed quarterly KeyMetricsReport "
                                "due to newer monthly inputs."
                            ),
                            event_code="key_metrics_quarter_refreshed",
                            fiscal_year=fiscal_year,
                            fiscal_quarter=fiscal_quarter,
                            period_start=str(quarter_report.period_start),
                            period_end=str(quarter_report.period_end),
                            task_id=task_id,
                        )

    # Fiscal year

    # Any fiscal year that has at least one quarter row should have a FY rollup
    fiscal_years_with_quarters = set(
        KeyMetricsReport.objects.filter(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY
        ).values_list("fiscal_year", flat=True)
    )

    for fiscal_year in sorted(fiscal_years_with_quarters):
        fiscal_year_report = KeyMetricsReport.objects.filter(
            period_type=KeyMetricsReport.PeriodType.FISCAL_YEAR,
            fiscal_year=fiscal_year,
        ).first()

        if recompute_all:
            year_report = KeyMetricsReport.upsert_fiscal_year(fiscal_year=fiscal_year)
            if year_report is not None:
                rows_changed += 1
                structured_logger.info(
                    "Upserted fiscal-year KeyMetricsReport.",
                    event_code="key_metrics_year_upserted",
                    fiscal_year=fiscal_year,
                    period_start=str(year_report.period_start),
                    period_end=str(year_report.period_end),
                    task_id=task_id,
                )
            continue

        if fiscal_year_report is None:
            year_report = KeyMetricsReport.upsert_fiscal_year(fiscal_year=fiscal_year)
            if year_report is not None:
                rows_changed += 1
                structured_logger.info(
                    "Created missing fiscal-year KeyMetricsReport.",
                    event_code="key_metrics_year_created",
                    fiscal_year=fiscal_year,
                    period_start=str(year_report.period_start),
                    period_end=str(year_report.period_end),
                    task_id=task_id,
                )
        else:
            # Refresh if any constituent QUARTER rows are newer than the FY row
            quarter_newer_exists = KeyMetricsReport.objects.filter(
                period_type=KeyMetricsReport.PeriodType.QUARTERLY,
                fiscal_year=fiscal_year,
                updated_on__gt=fiscal_year_report.updated_on,
            ).exists()

            if quarter_newer_exists:
                year_report = KeyMetricsReport.upsert_fiscal_year(
                    fiscal_year=fiscal_year
                )
                if year_report is not None:
                    rows_changed += 1
                    structured_logger.info(
                        (
                            "Refreshed fiscal-year KeyMetricsReport "
                            "due to newer quarterly inputs."
                        ),
                        event_code="key_metrics_year_refreshed",
                        fiscal_year=fiscal_year,
                        period_start=str(year_report.period_start),
                        period_end=str(year_report.period_end),
                        task_id=task_id,
                    )

    structured_logger.info(
        "Completed KeyMetricsReport build.",
        event_code="key_metrics_build_complete",
        rows_changed=rows_changed,
        task_id=task_id,
        recompute_all=recompute_all,
    )
    return rows_changed


@celery_app.task
def calculate_difficulty_values(asset_qs=None):
    """
    Calculate the difficulty scores for the provided AssetQuerySet and update
    the Asset records for changed difficulty values
    """

    if asset_qs is None:
        asset_qs = Asset.objects.published()

    asset_qs = asset_qs.add_contribution_counts()

    updated_count = 0

    # We'll process assets in chunks using an iterator to avoid saving objects
    # which will never be used again in memory. We will find assets which have a
    # difficulty value which is not the same as the value stored in the database
    # and pass them to bulk_update() to be saved in a single query.
    for asset_chunk in chunked(asset_qs.iterator(), 500):
        changed_assets = []

        for asset in asset_chunk:
            difficulty = asset.transcription_count * (
                asset.transcriber_count + asset.reviewer_count
            )
            if difficulty != asset.difficulty:
                asset.difficulty = difficulty
                changed_assets.append(asset)

        if changed_assets:
            # We will only save the new difficulty score both for performance
            # and to avoid any possibility of race conditions causing stale data
            # to be saved:
            Asset.objects.bulk_update(changed_assets, ["difficulty"])
            updated_count += len(changed_assets)

    return updated_count


@celery_app.task
def populate_asset_years():
    """
    Pull out date info from raw Item metadata and populate it for each Asset
    """

    asset_qs = Asset.objects.prefetch_related("item")

    updated_count = 0

    for asset_chunk in chunked(asset_qs, 500):
        changed_assets = []

        for asset in asset_chunk:
            metadata = asset.item.metadata

            year = None
            for date_outer in metadata["item"]["dates"]:
                for date_inner in date_outer.keys():
                    year = date_inner
                    break  # We don't support multiple values

            if asset.year != year:
                asset.year = year
                changed_assets.append(asset)

        if changed_assets:
            Asset.objects.bulk_update(changed_assets, ["year"])
            updated_count += len(changed_assets)

    return updated_count


@celery_app.task
def create_opensearch_indices():
    """Create the opensearch indices, if they don't already exist."""
    call_command(
        "opensearch", "index", "create", verbosity=2, force=True, ignore_error=True
    )


@celery_app.task
def delete_opensearch_indices():
    """Delete opensearch indices - index and data (a.k.a. documents)."""
    call_command("opensearch", "index", "delete", force=True, ignore_error=True)


@celery_app.task
def rebuild_opensearch_indices():
    """Deletes, then creates opensearch indices."""
    call_command(
        "opensearch", "index", "rebuild", verbosity=2, force=True, ignore_error=True
    )


@celery_app.task
def populate_opensearch_users_indices():
    """
    Populate the "users" OpenSearch index. This function loads the indices
    in Opensearch as defined in the UserDocument class to make it searchable
    and accessible for queries in the Opensearch Dashboards.
    """
    call_command(
        "opensearch", "document", "index", "--indices", "users", "--force", "--parallel"
    )


@celery_app.task
def populate_opensearch_assets_indices():
    """
    Populate the "assets" OpenSearch index. This function loads the indices
    in Opensearch as defined in the AssetDocument class to make it searchable
    and accessible for queries in the Opensearch Dashboards.
    """
    call_command(
        "opensearch",
        "document",
        "index",
        "--indices",
        "assets",
        "--force",
        "--parallel",
    )


@celery_app.task
def populate_opensearch_indices():
    """
    Populate the OpenSearch index with all documents.
    --force - stops interactive confirmation prompt.
    --parallel - invokes opensearch in parallel mode.
    """
    call_command("opensearch", "document", "index", "--force", "--parallel")


def _populate_activity_table(campaigns):
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
def populate_completed_campaign_counts():
    # this task creates records in the UserProfileActivity table for campaigns
    # that are completed or have status == RETIRED (but have not yet actually
    # been retired). It should be run once, after the table has initially been
    # created
    # in my local env, this task took ~10 minutes to complete
    campaigns = Campaign.objects.exclude(status=Campaign.Status.ACTIVE)
    _populate_activity_table(campaigns)


@celery_app.task
def populate_active_campaign_counts():
    active_campaigns = Campaign.objects.filter(status=Campaign.Status.ACTIVE)
    _populate_activity_table(active_campaigns)


@celery_app.task(ignore_result=True)
def retire_campaign(campaign_id):
    # Entry point to the retirement process
    campaign = Campaign.objects.get(id=campaign_id)
    logger.debug("Retiring %s (%s)", campaign, campaign.id)
    progress, created = CampaignRetirementProgress.objects.get_or_create(
        campaign=campaign
    )
    if created:
        # We want to set totals on a newly created progress object
        # but not on one that already exists. This allows us to keep proper
        # track of the full progress if the process is stopped and resumed
        projects = campaign.project_set.values_list("id", flat=True)
        items = Item.objects.filter(project__id__in=projects).values_list(
            "id", flat=True
        )
        assets = Asset.objects.filter(item__id__in=items).values_list("id", flat=True)
        progress.project_total = len(projects)
        progress.item_total = len(items)
        progress.asset_total = len(assets)
        progress.save()
    if campaign.status != Campaign.Status.RETIRED:
        logger.debug("Setting campaign status to retired")
        # We want to make sure the status is set to Retired before
        # we start removing information so the front-end is pulling
        # from archived data rather than live
        campaign.status = Campaign.Status.RETIRED
        campaign.save()
    remove_next_project.delay(campaign.id)
    return progress


@celery_app.task(ignore_result=True)
def project_removal_success(project_id, campaign_id):
    logger.debug("Updating progress for campaign %s", campaign_id)
    logger.debug("Project id %s", project_id)
    with transaction.atomic():
        progress = CampaignRetirementProgress.objects.select_for_update().get(
            campaign__id=campaign_id
        )
        progress.projects_removed = F("projects_removed") + 1
        progress.removal_log.append(
            {
                "type": "project",
                "id": project_id,
            }
        )
        progress.save()
        logger.debug("Progress updated for %s", campaign_id)
    remove_next_project.delay(campaign_id)


@celery_app.task(ignore_result=True)
def remove_next_project(campaign_id):
    campaign = Campaign.objects.get(id=campaign_id)
    logger.debug("Removing projects for %s (%s)", campaign, campaign.id)
    try:
        project = campaign.project_set.all()[0]
        remove_next_item.delay(project.id)
    except IndexError:
        # This means all projects are deleted, which means the
        # campaign is fully retired.
        logger.debug("Updating progress for campaign %s", campaign_id)
        logger.debug("Retirement complete for campaign %s", campaign_id)
        with transaction.atomic():
            progress = CampaignRetirementProgress.objects.select_for_update().get(
                campaign__id=campaign_id
            )
            progress.complete = True
            progress.completed_on = timezone.now()
            progress.save()
        logger.debug("Progress updated for %s", campaign_id)


@celery_app.task(ignore_result=True)
def item_removal_success(item_id, campaign_id, project_id):
    logger.debug("Updating progress for campaign %s", campaign_id)
    logger.debug("Item id %s", item_id)
    with transaction.atomic():
        progress = CampaignRetirementProgress.objects.select_for_update().get(
            campaign__id=campaign_id
        )
        progress.items_removed = F("items_removed") + 1
        progress.removal_log.append(
            {
                "type": "item",
                "id": item_id,
            }
        )
        progress.save()
    logger.debug("Progress updated for %s", campaign_id)
    remove_next_item.delay(project_id)


@celery_app.task(ignore_result=True)
def remove_next_item(project_id):
    project = Project.objects.get(id=project_id)
    logger.debug("Removing items for %s (%s)", project, project.id)
    try:
        item = project.item_set.all()[0]
        remove_next_assets.delay(item.id)
    except IndexError:
        # No more items remain for this project, so we can now delete
        # the project
        logger.debug("All items remoed for %s (%s)", project, project.id)
        campaign_id = project.campaign.id
        project_id = project.id
        project.delete()
        project_removal_success.delay(project_id, campaign_id)


@celery_app.task(ignore_result=True)
def assets_removal_success(asset_ids, campaign_id, item_id):
    logger.debug("Updating progress for campaign %s", campaign_id)
    logger.debug("Asset ids %s", asset_ids)
    with transaction.atomic():
        progress = CampaignRetirementProgress.objects.select_for_update().get(
            campaign__id=campaign_id
        )
        progress.assets_removed = F("assets_removed") + len(asset_ids)
        for asset_id in asset_ids:
            progress.removal_log.append(
                {
                    "type": "asset",
                    "id": asset_id,
                }
            )
        progress.save()
    logger.debug("Progress updated for %s", campaign_id)
    remove_next_assets.delay(item_id)


@celery_app.task(ignore_result=True)
def remove_next_assets(item_id):
    item = Item.objects.get(id=item_id)
    campaign_id = item.project.campaign.id
    logger.debug("Removing assets for %s (%s)", item, item.id)
    assets = item.asset_set.all()
    if not assets:
        # No assets remain for this item, so we can safely delete it
        logger.debug("All assets removed for %s (%s)", item, item.id)
        item_id = item.id
        project_id = item.project.id
        item.delete()
        item_removal_success.delay(item_id, campaign_id, project_id)
    else:
        # We delete assets in chunks of 10 in order to not lock up the database
        # for a long period of time.
        chord(delete_asset.s(asset.id) for asset in assets[:10])(
            assets_removal_success.s(campaign_id, item.id)
        )


@celery_app.task
def delete_asset(asset_id):
    asset = Asset.objects.get(id=asset_id)
    asset_id = asset.id
    logger.debug("Deleting asset %s (%s)", asset, asset_id)
    # We explicitly delete the storage image, though
    # this should be removed anyway when the asset is deleted
    asset.storage_image.delete(save=False)
    asset.delete()
    logger.debug("Asset %s (%s) deleted", asset, asset_id)

    return asset_id


@celery_app.task(ignore_result=True)
def populate_resource_files():
    client = boto3.client("s3")
    response = client.list_objects_v2(
        Bucket=settings.S3_BUCKET_NAME, Prefix="cm-uploads/resources/"
    )
    files = response["Contents"]
    for file in files:
        path = file["Key"]
        if path == "cm-uploads/resources/":
            continue
        try:
            ResourceFile.objects.get(resource=path)
        except ResourceFile.DoesNotExist:
            filename, extension = os.path.splitext(os.path.basename(path))
            name = "%s-%s" % (filename, extension[1:])
            ResourceFile.objects.create(resource=path, name=name)


@celery_app.task(ignore_result=True)
def fix_storage_images(campaign_slug=None, asset_start_id=None):
    if campaign_slug:
        campaign = Campaign.objects.get(slug=campaign_slug)
        asset_queryset = Asset.objects.filter(item__project__campaign=campaign)
    else:
        asset_queryset = Asset.objects.all()

    if asset_start_id:
        asset_queryset = asset_queryset.filter(id__gte=asset_start_id)

    count = 0
    full_count = asset_queryset.count()
    logger.debug("Checking storage image on %s assets", full_count)
    for asset in asset_queryset.order_by("id"):
        count += 1
        if asset.storage_image:
            if not asset.storage_image.storage.exists(asset.storage_image.name):
                logger.info("Storage image does not exist for %s (%s)", asset, asset.id)
                item = asset.item
                download_url = asset.download_url
                asset_filename = os.path.join(
                    item.project.campaign.slug,
                    item.project.slug,
                    item.item_id,
                    "%d.jpg" % asset.sequence,
                )
                try:
                    with NamedTemporaryFile(mode="x+b") as temp_file:
                        resp = requests.get(download_url, stream=True, timeout=30)
                        resp.raise_for_status()

                        for chunk in resp.iter_content(chunk_size=256 * 1024):
                            temp_file.write(chunk)

                        # Rewind the tempfile back to the first byte so we can
                        temp_file.flush()
                        temp_file.seek(0)

                        ASSET_STORAGE.save(asset_filename, temp_file)

                except Exception:
                    logger.exception(
                        "Unable to download %s to %s", download_url, asset_filename
                    )
                    raise
                logger.info("Storage image downloaded for  %s (%s)", asset, asset.id)
        logger.debug("Storage image checked for %s (%s)", asset, asset.id)
        logger.debug("%s / %s (%s%%)", count, full_count, str(count / full_count * 100))


@celery_app.task(ignore_result=True)
def clear_sessions():
    # This clears expired Django sessions in the database
    call_command("clearsessions")


@celery_app.task(ignore_result=True)
def unusual_activity(ignore_env=False):
    """
    Locate pages that were improperly transcribed or reviewed.
    """
    # Don't bother running unless we're in the prod env
    if settings.CONCORDIA_ENVIRONMENT == "production" or ignore_env:
        site = Site.objects.get_current()
        display_time = timezone.localtime().strftime("%b %d %Y, %I:%M %p")
        ONE_DAY_AGO = timezone.now() - datetime.timedelta(days=1)
        title = "Unusual User Activity Report for " + display_time
        if ignore_env:
            title += " [%s]" % ENV_MAPPING[settings.CONCORDIA_ENVIRONMENT]
        context = {
            "title": title,
            "domain": "https://" + site.domain,
            "transcriptions": Transcription.objects.transcribe_incidents(ONE_DAY_AGO),
            "reviews": Transcription.objects.review_incidents(ONE_DAY_AGO),
        }

        text_body_template = loader.get_template("emails/unusual_activity.txt")
        text_body_message = text_body_template.render(context)

        html_body_template = loader.get_template("emails/unusual_activity.html")
        html_body_message = html_body_template.render(context)

        to_email = ["rsar@loc.gov"]
        if settings.DEFAULT_TO_EMAIL:
            to_email.append(settings.DEFAULT_TO_EMAIL)
        message = EmailMultiAlternatives(
            subject=context["title"],
            body=text_body_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=to_email,
            reply_to=[settings.DEFAULT_FROM_EMAIL],
        )
        message.attach_alternative(html_body_message, "text/html")
        message.send()


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=5,
    retry_kwargs={"max_retries": 5, "countdown": 5},
)
def update_useractivity_cache(self, user_id, campaign_id, attr_name, *args, **kwargs):
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
def update_userprofileactivity_from_cache(self):
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
                    user, campaign.id, "transcribe_count", updates_by_user[user_id][0]
                )
                update_userprofileactivity_table(
                    user, campaign.id, "review_count", updates_by_user[user_id][1]
                )
                structured_logger.debug(
                    "Updated activity counts for user",
                    event_code="update_userprofileactivity_from_cache_database_write",
                    user=user_id,
                )
        else:
            structured_logger.debug(
                "Cache contained no updates for key. Skipping",
                event_code="update_userprofileactivity_from_cache_no_updates",
                key=key,
            )


@celery_app.task(bind=True, ignore_result=True)
@locked_task
def populate_next_transcribable_for_campaign(self, campaign_id):
    """
    Populate the cache table of next transcribable assets for a given campaign.

    This task checks how many transcribable assets are still needed for the campaign,
    finds eligible assets, and inserts them into the NextTranscribableCampaignAsset
    table up to the target count.

    Only a single instance of the task will run at a time for a particular campaign_id,
    using the cache locking system to avoid duplication. This can be overriden with
    the `force` kwarg, which is stripped out by the decorator and not passed to the
    task itself. See the `locked_task` documentation for more information.

    Args:
        campaign_id (int): The primary key of the Campaign to process.
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
    Populate the cache table of next transcribable assets for a given topic.

    This task checks how many transcribable assets are still needed for the topic,
    finds eligible assets, and inserts them into the NextTranscribableTopicAsset table
    up to the target count.

    Only a single instance of the task will run at a time for a particular topic_id,
    using the cache locking system to avoid duplication. This can be overriden with
    the `force` kwarg, which is stripped out by the decorator and not passed to the
    task itself. See the `locked_task` documentation for more information.

    Args:
        topic_id (int): The primary key of the Topic to process.
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
def populate_next_reviewable_for_campaign(self, campaign_id):
    """
    Populate the cache table of next reviewable assets for a given campaign.

    This task checks how many reviewable assets are still needed for the campaign,
    finds eligible assets, and inserts them into the NextReviewableCampaignAsset table
    up to the target count.

    The task prioritizes assets not transcribed by transcribers already in the table,
    to avoid review bottlenecks.

    Only a single instance of the task will run at a time for a particular campaign_id,
    using the cache locking system to avoid duplication. This can be overriden with
    the `force` kwarg, which is stripped out by the decorator and not passed to the
    task itself. See the `locked_task` documentation for more information.

    Args:
        campaign_id (int): The primary key of the Campaign to process.
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
        # the situation where all possible reviewable assets have the same transcriber
        # (since that would mean that user would miss the cache table when they try
        # to review).
        # If that's impossible, we just take whatever assets we can; that means only
        # these transcribers have reviewable assets in the campaign
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
    Populate the cache table of next reviewable assets for a given topic.

    This task checks how many reviewable assets are still needed for the topic,
    finds eligible assets, and inserts them into the NextReviewableTopicAsset table
    up to the target count.

    The task prioritizes assets not transcribed by transcribers already in the table,
    to avoid review bottlenecks.

    Only a single instance of the task will run at a time for a particular topic_id,
    using the cache locking system to avoid duplication. This can be overriden with
    the `force` kwarg, which is stripped out by the decorator and not passed to the
    task itself. See the `locked_task` documentation for more information.

    Args:
        topic_id (int): The primary key of the Topic to process.
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
        # the situation where all possible reviewable assets have the same transcriber
        # (since that would mean that user would miss the cache table when they try
        # to review).
        # If that's impossible, we just take whatever assets we can; that means only
        # these transcribers have reviewable assets in the campaign
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
def clean_next_transcribable_for_campaign(self, campaign_id):
    """
    Removes invalid cached transcribable assets for a campaign and repopulates the
    cache.

    Invalid assets include those that are reserved or no longer eligible for
    transcription based on their transcription status. After cleaning, the corresponding
    populate task is queued to restore the cache to the target count.

    Args:
        campaign_id (int): The ID of the campaign to clean.
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
    Removes invalid cached transcribable assets for a topic and repopulates the cache.

    Invalid assets include those that are reserved or no longer eligible for
    transcription based on their transcription status. After cleaning, the corresponding
    populate task is queued to restore the cache to the target count.

    Args:
        topic_id (int): The ID of the topic to clean.
    """

    for next_asset in find_invalid_next_transcribable_topic_assets(topic_id):
        try:
            next_asset.delete()
        except Exception:
            logger.exception("Error deleting cached asset %s", next_asset.id)
    logger.info("Spawning populate_next_transcribable_for_topic for topic %s", topic_id)
    populate_next_transcribable_for_topic.delay(topic_id)


@celery_app.task(bind=True, ignore_result=True)
@locked_task
def clean_next_reviewable_for_campaign(self, campaign_id):
    """
    Removes invalid cached reviewable assets for a campaign and repopulates the cache.

    Invalid assets include those that no longer have transcription status SUBMITTED and
    are therefore not eligible for review. After cleaning, the corresponding populate
    task is queued to restore the cache to the target count.

    Args:
        campaign_id (int): The ID of the campaign to clean.
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
    Removes invalid cached reviewable assets for a topic and repopulates the cache.

    Invalid assets include those that no longer have transcription status SUBMITTED and
    are therefore not eligible for review. After cleaning, the corresponding populate
    task is queued to restore the cache to the target count.

    Args:
        topic_id (int): The ID of the topic to clean.
    """

    for next_asset in find_invalid_next_reviewable_topic_assets(topic_id):
        try:
            next_asset.delete()
        except Exception:
            logger.exception("Error deleting cached asset %s", next_asset.id)
    logger.info("Spawning populate_next_reviewable_for_topic for topic %s", topic_id)
    populate_next_reviewable_for_topic.delay(topic_id)


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


@celery_app.task(bind=True, ignore_result=True)
@locked_task
def populate_asset_status_visualization_cache(self):
    """
    Queries live Asset objects for all ACTIVE campaigns and builds a dataset:
        - `status_labels`: [
                "Not Started",
                "In Progress",
                "Needs Review",
                "Completed"
          ]
        - `total_counts`: [
                count_not_started,
                count_in_progress,
                count_submitted,
                count_completed
          ]
        - `csv_url`: URL to download a CSV of the data
    """
    visualization_cache = caches["visualization_cache"]
    cache_key = "asset-status-overview"
    csv_path = "visualization_exports/page-status-active-campaigns.csv"

    structured_logger.debug(
        "Starting asset status visualization task.",
        event_code="asset_status_vis_start",
    )

    campaign_ids = list(
        Campaign.objects.published().listed().active().values_list("id", flat=True)
    )

    status_keys = [key for key, _ in TranscriptionStatus.CHOICES]
    status_labels = [TranscriptionStatus.CHOICE_MAP[key] for key in status_keys]

    # Aggregate counts across all active campaigns
    status_counts_qs = (
        Asset.objects.filter(campaign_id__in=campaign_ids)
        .values("transcription_status")
        .annotate(cnt=Count("id"))
    )
    counts_map = {row["transcription_status"]: row["cnt"] for row in status_counts_qs}
    total_counts = [counts_map.get(status, 0) for status in status_keys]

    structured_logger.debug(
        "Aggregated asset counts by status.",
        event_code="asset_status_vis_counts",
        active_campaign_count=len(campaign_ids),
        total_counts=total_counts,
    )

    # If data unchanged, skip CSV + cache update
    existing = visualization_cache.get(cache_key)
    if isinstance(existing, dict) and existing.get("total_counts") == total_counts:
        structured_logger.info(
            "Asset status data unchanged; skipping CSV and cache update.",
            event_code="asset_status_vis_unchanged",
            total_counts=total_counts,
        )
        return
    elif isinstance(existing, dict):
        # We want the existing URL in case the upload fails later
        overview_csv_url = existing.get("csv_url")
    else:
        overview_csv_url = None

    overview_csv = StringIO(newline="")
    overview_writer = csv.writer(overview_csv)
    overview_writer.writerow(["Status", "Count"])
    for label, count in zip(status_labels, total_counts, strict=True):
        overview_writer.writerow([label, count])
    overview_csv_content = overview_csv.getvalue()

    try:
        VISUALIZATION_STORAGE.save(csv_path, ContentFile(overview_csv_content))
        overview_csv_url = VISUALIZATION_STORAGE.url(csv_path)
        structured_logger.debug(
            "CSV saved for asset status visualization.",
            event_code="asset_status_vis_csv_saved",
            csv_path=csv_path,
            byte_length=len(overview_csv_content.encode("utf-8")),
            csv_url=overview_csv_url,
        )
    except Exception:
        if overview_csv_url is None:
            structured_logger.exception(
                (
                    "CSV upload failed for asset status visualization and "
                    "no existing CSV URL could be determined"
                ),
                event_code="asset_status_vis_csv_missing_url_error",
                csv_path=csv_path,
            )
            raise
        structured_logger.exception(
            "CSV upload failed for asset status visualization.",
            event_code="asset_status_vis_csv_error",
            csv_path=csv_path,
        )

    # Update cache
    overview_payload = {
        "status_labels": status_labels,
        "total_counts": total_counts,
        "csv_url": overview_csv_url,
    }
    visualization_cache.set(cache_key, overview_payload, None)

    structured_logger.debug(
        "Asset status visualization cache updated.",
        event_code="asset_status_vis_cache_set",
        cache_key=cache_key,
        total_counts=total_counts,
    )

    structured_logger.debug(
        "Asset status visualization task completed successfully.",
        event_code="asset_status_vis_complete",
    )


@celery_app.task(bind=True, ignore_result=True)
@locked_task
def populate_daily_activity_visualization_cache(self):
    """
    Queries total SiteReport objects for the past 28 days and builds a dataset.

    The dataset contains:
        - `labels`: [ "YYYY-MM-DD", ..., ] (28 dates)
        - `transcription_datasets`: [
              {
                  "label": "Transcriptions",
                  "data": [ daily_total, daily_total, ... ],
              },
              {
                  "label": "Reviews",
                  "data": [ daily_total, daily_total, ... ],
              },
          ]
        - `csv_url`: URL to download a CSV of the data
    """
    visualization_cache = caches["visualization_cache"]
    cache_key = "daily-transcription-activity-last-28-days"
    csv_path = "visualization_exports/daily-transcription-activity-last-28-days.csv"

    structured_logger.debug(
        "Starting daily activity visualization task.",
        event_code="daily_activity_vis_start",
    )

    yesterday = timezone.now().date() - timedelta(days=1)
    start_date = yesterday - timedelta(days=27)
    date_range = [start_date + timedelta(days=i) for i in range(28)]
    date_strings = [d.strftime("%Y-%m-%d") for d in date_range]

    reports = SiteReport.objects.filter(
        report_name=SiteReport.ReportName.TOTAL,
        created_on__date__in=date_range,
    )
    report_lookup = {report.created_on.date(): report for report in reports}

    # Find the most recent SiteReport BEFORE the first of our dates, if any
    prev_report = (
        SiteReport.objects.filter(
            report_name=SiteReport.ReportName.TOTAL,
            created_on__date__lt=start_date,
        )
        .order_by("-created_on")
        .first()
    )
    prev_cumulative = prev_report.transcriptions_saved if prev_report else 0
    running_prev = prev_cumulative

    transcriptions = []
    reviews = []

    for report_date in date_range:
        sitereport = report_lookup.get(report_date)
        if sitereport:
            cumulative = sitereport.transcriptions_saved or 0
            daily_saved = cumulative - running_prev
            if daily_saved < 0:
                daily_saved = 0
            running_prev = cumulative
            daily_review = sitereport.daily_review_actions or 0
        else:
            daily_saved = 0
            daily_review = 0

        transcriptions.append(daily_saved)
        reviews.append(daily_review)

    structured_logger.debug(
        "Compiled daily activity series.",
        event_code="daily_activity_vis_series_compiled",
        start_date=start_date.isoformat(),
        end_date=yesterday.isoformat(),
        transcriptions_total=sum(transcriptions),
        reviews_total=sum(reviews),
    )

    # If data unchanged, skip CSV + cache update
    existing = visualization_cache.get(cache_key)
    if isinstance(existing, dict):
        prev_series = existing.get("transcription_datasets") or []
        prev_transcriptions = next(
            (
                ds.get("data")
                for ds in prev_series
                if ds.get("label") == "Transcriptions"
            ),
            None,
        )
        prev_reviews = next(
            (ds.get("data") for ds in prev_series if ds.get("label") == "Reviews"),
            None,
        )
        if prev_transcriptions == transcriptions and prev_reviews == reviews:
            structured_logger.info(
                "Daily activity data unchanged; skipping CSV and cache update.",
                event_code="daily_activity_vis_unchanged",
            )
            return
        else:
            csv_url = existing.get("csv_url")
    else:
        csv_url = None

    data = {
        "labels": date_strings,
        "transcription_datasets": [
            {"label": "Transcriptions", "data": transcriptions},
            {"label": "Reviews", "data": reviews},
        ],
    }

    csv_output = StringIO(newline="")
    writer = csv.writer(csv_output)
    writer.writerow(["Date", "Transcriptions", "Reviews"])
    for i in range(28):
        writer.writerow([date_strings[i], transcriptions[i], reviews[i]])
    csv_content = csv_output.getvalue()

    try:
        VISUALIZATION_STORAGE.save(csv_path, ContentFile(csv_content))
        csv_url = VISUALIZATION_STORAGE.url(csv_path)
        structured_logger.debug(
            "CSV saved for daily activity visualization.",
            event_code="daily_activity_vis_csv_saved",
            csv_path=csv_path,
            byte_length=len(csv_content.encode("utf-8")),
            csv_url=csv_url,
        )
    except Exception:
        if csv_url is None:
            structured_logger.exception(
                (
                    "CSV upload failed for daily activity visualization and "
                    "no existing CSV URL could be determined"
                ),
                event_code="daily_activity_vis_csv_missing_url_error",
                csv_path=csv_path,
            )
            raise
        structured_logger.exception(
            "CSV upload failed for daily activity visualization.",
            event_code="daily_activity_vis_csv_error",
            csv_path=csv_path,
        )

    data["csv_url"] = csv_url
    visualization_cache.set(cache_key, data, None)

    structured_logger.debug(
        "Daily activity visualization cache updated.",
        event_code="daily_activity_vis_cache_set",
        cache_key=cache_key,
    )

    structured_logger.debug(
        "Daily activity visualization task completed successfully.",
        event_code="daily_activity_vis_complete",
    )


@celery_app.task(bind=True, ignore_result=True)
@locked_task
def fetch_and_cache_blog_images(self):
    for item in fetch_blog_posts():
        link = item.find("link")
        if link is not None:
            extract_og_image(link.text)


# TODO: remove download_item_thumbnail_task once `item.thumbnail_url` is removed


@celery_app.task(
    bind=True,
    autoretry_for=(requests.RequestException,),
    retry_backoff=5,
    retry_kwargs={"max_retries": 5, "countdown": 5},
)
def download_item_thumbnail_task(
    self,
    item_id: int,
    force: bool = False,
) -> str:
    """
    Fetch an Item and ensure its thumbnail_image is populated.

    The Item's `thumbnail_url` field is used as the source of the download.

    Args:
        item_id: Primary key of the Item to process.
        force: Overwrite an existing thumbnail if True.

    Returns:
        Storage path of the saved image, or a skip message.

    Raises:
        ValueError: If `Item.thumbnail_url` is unavailable.
        requests.RequestException: Network errors (auto-retried).
    """
    from importer.tasks.items import download_and_set_item_thumbnail

    with transaction.atomic():
        item = (
            Item.objects.select_for_update(of=("self",))
            .only("id", "thumbnail_url", "thumbnail_image", "item_id")
            .get(pk=item_id)
        )

    src_url = item.thumbnail_url
    if not src_url:
        msg = "No thumbnail URL available."
        logger.info("download_item_thumbnail_task: %s item_id=%s", msg, item_id)
        return msg

    return download_and_set_item_thumbnail(item, src_url, force=force)


# TODO: remove download_missing_thumbnails_task once `item.thumbnail_url` is removed


@celery_app.task(bind=True)
def download_missing_thumbnails_task(
    self,
    project_id: Optional[int] = None,
    batch_size: int = 10,
    limit: Optional[int] = None,
    force: bool = False,
) -> int:
    """
    Spawn per-item download tasks for items missing thumbnails in chunks.

    This finds Items that have a non-empty thumbnail_url but no stored
    thumbnail_image. It then executes per-item tasks in chunks of `batch_size`,
    waiting for each chunk to finish before starting the next.

    Args:
        project_id: Optional project filter.
        batch_size: Number of parallel tasks per wave.
        limit: Optional cap on total items processed.
        force: Overwrite existing thumbnails if true.

    Returns:
        Count of items scheduled/processed.
    """
    qs = Item.objects.all()

    if project_id is not None:
        qs = qs.filter(project_id=project_id)

    qs = qs.filter(
        Q(thumbnail_url__isnull=False)
        & ~Q(thumbnail_url="")
        & (Q(thumbnail_image__isnull=True) | Q(thumbnail_image=""))
    ).order_by("pk")

    if limit is not None:
        qs = qs[:limit]

    ids = list(qs.values_list("pk", flat=True))
    total = len(ids)
    if total == 0:
        logger.info("download_missing_thumbnails_task: nothing to do.")
        return 0

    # Process in waves of `batch_size`, waiting between waves.
    for i in range(0, total, batch_size):
        chunk = ids[i : i + batch_size]
        task_group = group(
            download_item_thumbnail_task.s(item_id, force=force) for item_id in chunk
        )
        result = task_group.apply_async()
        # Block this task until the chunk finishes; then schedule next.
        result.get(disable_sync_subtasks=False)

    logger.info(
        "download_missing_thumbnails_task: processed %s items in chunks of %s",
        total,
        batch_size,
    )
    return total
