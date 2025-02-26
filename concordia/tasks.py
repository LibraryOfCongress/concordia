import datetime
import os.path
from logging import getLogger
from tempfile import NamedTemporaryFile

import boto3
import requests
from celery import chord
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.core.management import call_command
from django.db import transaction
from django.db.models import Count, F, Q
from django.template import loader
from django.utils import timezone
from more_itertools.more import chunked

from concordia.models import (
    ONE_DAY,
    ONE_DAY_AGO,
    Asset,
    AssetTranscriptionReservation,
    Campaign,
    CampaignRetirementProgress,
    Item,
    Project,
    ResourceFile,
    SiteReport,
    Tag,
    Topic,
    Transcription,
    UserAssetTagCollection,
    UserProfileActivity,
    update_userprofileactivity_table,
)
from concordia.signals.signals import reservation_released
from concordia.storage import ASSET_STORAGE
from concordia.utils import get_anonymous_user

from .celery import app as celery_app

logger = getLogger(__name__)


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
    return Transcription.objects.filter(
        Q(accepted__gte=ONE_DAY_AGO)
        | Q(created_on__gte=ONE_DAY_AGO)
        | Q(rejected__gte=ONE_DAY_AGO)
        | Q(submitted__gte=ONE_DAY_AGO)
        | Q(updated_on__gte=ONE_DAY_AGO)
    )


def _daily_active_users():
    transcriptions = _recent_transcriptions()
    transcriber_ids = transcriptions.values_list("user", flat=True).distinct()
    reviewer_ids = (
        transcriptions.exclude(reviewed_by__isnull=True)
        .values_list("reviewed_by", flat=True)
        .distinct()
    )
    return len(set(list(reviewer_ids) + list(transcriber_ids)))


@celery_app.task
def site_report():
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

    site_report = SiteReport()
    site_report.report_name = SiteReport.ReportName.TOTAL
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
    site_report.campaigns_published = campaigns_published
    site_report.campaigns_unpublished = campaigns_unpublished
    site_report.users_registered = users_registered
    site_report.users_activated = users_activated
    site_report.daily_active_users = _daily_active_users()
    site_report.save()

    for campaign in Campaign.objects.exclude(status=Campaign.Status.RETIRED):
        campaign_report(campaign)

    for topic in Topic.objects.all():
        topic_report(topic)

    retired_total_report()


def topic_report(topic):
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
    site_report.save()


def campaign_report(campaign):
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
    site_report.save()


def retired_total_report():
    site_reports = (
        SiteReport.objects.filter(campaign__status=Campaign.Status.RETIRED)
        .order_by("campaign_id", "-created_on")
        .distinct("campaign_id")
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
    total_site_report.save()


def site_reports_for_date(date):
    start = date - ONE_DAY
    return SiteReport.objects.filter(created_on__gte=start, created_on__lte=date)


def assets_for_date(date):
    start = date - ONE_DAY
    q_accepted = Q(
        transcription__accepted__gte=start, transcription__accepted__lte=date
    )
    q_rejected = Q(
        transcription__rejected__gte=start, transcription__rejected__lte=date
    )
    return Asset.objects.filter(q_accepted | q_rejected)


@celery_app.task(ignore_result=True)
def backfill_total(date, days):
    logger.info(
        "STARTING: Backfilling daily data for %s on %s",
        SiteReport.ReportName.TOTAL,
        date,
    )
    site_report = site_reports_for_date(date).filter(
        report_name=SiteReport.ReportName.TOTAL
    )[0]
    logger.info(
        "STARTING: Backfilling daily data for report %s (%s)", site_report.id, date
    )
    daily_review_actions = assets_for_date(date).count()
    logger.debug(
        "%s daily review actions for report %s (%s)",
        daily_review_actions,
        site_report.id,
        date,
    )
    site_report.daily_review_actions = daily_review_actions
    site_report.save()
    logger.info(
        "FINISHED: Backfilling daily data for %s on %s",
        SiteReport.ReportName.TOTAL,
        date,
    )
    logger.info("FINISHED: Backfilling daily data for all reports on %s", date)

    if days > 0:
        return backfill_topics.delay(date - ONE_DAY, days - 1)
    else:
        logger.info("Backfilling daily data complete")


@celery_app.task(ignore_result=True)
def backfill_next_campaign_report(date, days, site_report_ids):
    try:
        site_report_id = site_report_ids.pop()
    except IndexError:
        logger.info("FINISHED: Backfilling daily data for campaigns on %s", date)
        backfill_total.delay(date, days)
        return
    site_report = SiteReport.objects.get(id=site_report_id)
    logger.info(
        "STARTING: Backfilling daily data for report %s (%s)", site_report.id, date
    )
    daily_review_actions = (
        assets_for_date(date)
        .filter(item__project__campaign=site_report.campaign)
        .count()
    )
    logger.debug(
        "%s daily review actions for report %s (%s)",
        daily_review_actions,
        site_report.id,
        date,
    )
    site_report.daily_review_actions = daily_review_actions
    site_report.save()
    logger.info(
        "FINISHED: Backfilling daily data for report %s (%s)", site_report.id, date
    )
    return backfill_next_campaign_report.delay(date, days, site_report_ids)


@celery_app.task(ignore_result=True)
def backfill_campaigns(date, days):
    site_report_ids = list(
        site_reports_for_date(date)
        .filter(campaign__isnull=False)
        .values_list("id", flat=True)
    )
    logger.info("STARTING: Backfilling daily data for campaigns on %s", date)
    return backfill_next_campaign_report.delay(date, days, site_report_ids)


@celery_app.task(ignore_result=True)
def backfill_next_topic_report(date, days, site_report_ids):
    try:
        site_report_id = site_report_ids.pop()
    except IndexError:
        logger.info("FINISHED: Backfilling daily data for topics on %s", date)
        backfill_campaigns.delay(date, days)
        return
    site_report = SiteReport.objects.get(id=site_report_id)
    logger.info(
        "STARTING: Backfilling daily data for report %s (%s)", site_report.id, date
    )
    daily_review_actions = (
        assets_for_date(date).filter(item__project__topics=site_report.topic).count()
    )
    logger.debug(
        "%s daily review actions for report %s (%s)",
        daily_review_actions,
        site_report.id,
        date,
    )
    site_report.daily_review_actions = daily_review_actions
    site_report.save()
    logger.info(
        "FINISHED: Backfilling daily data for report %s (%s)", site_report.id, date
    )
    return backfill_next_topic_report.delay(date, days, site_report_ids)


@celery_app.task(ignore_result=True)
def backfill_topics(date, days):
    site_report_ids = list(
        site_reports_for_date(date)
        .filter(topic__isnull=False)
        .values_list("id", flat=True)
    )
    logger.info("STARTING: Backfilling daily data for topics on %s", date)
    return backfill_next_topic_report.delay(date, days, site_report_ids)


@celery_app.task(ignore_result=True)
def backfill_daily_data(start, days):
    date = timezone.make_aware(datetime.datetime(**start))
    logger.info("Backfilling daily data for the %s days before %s", days, date)
    logger.info("STARTED: Backfilling daily data for all reports on %s", date)
    return backfill_topics.delay(date, days - 1)


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
def populate_storage_image_values(asset_qs=None):
    """
    For Assets that existed prior to implementing the storage_image ImageField, build
    the relative S3 storage key for the asset and update the storage_image value
    """
    # As a reference point - how many records have a null storage image field?
    asset_storage_qs = Asset.objects.filter(
        storage_image__isnull=True
    ) | Asset.objects.filter(storage_image__exact="")
    storage_image_empty_count = asset_storage_qs.count()
    asset_qs = (
        Asset.objects.filter(storage_image__isnull=True)
        | Asset.objects.filter(storage_image__exact="")
        .order_by("id")
        .select_related("item__project__campaign")
        .only(
            "id",
            "storage_image",
            "media_url",
            "item",
            "item__item_id",
            "item__project",
            "item__project__slug",
            "item__project__campaign",
            "item__project__campaign__slug",
        )[:5000]
    )
    logger.debug("Total Storage image empty count %s", storage_image_empty_count)
    logger.debug("Start storage image chunking")

    updated_count = 0

    # We'll process assets in chunks using an iterator to avoid saving objects
    # which will never be used again in memory. We will build the S3 relative key for
    # each existing asset and pass them to bulk_update() to be saved in a single query.
    for asset_chunk in chunked(asset_qs.iterator(), 1000):
        for asset in asset_chunk:
            asset.storage_image = "/".join(
                [
                    asset.item.project.campaign.slug,
                    asset.item.project.slug,
                    asset.item.item_id,
                    asset.media_url,
                ]
            )

        # We will only save the new storage image value both for performance
        # and to avoid any possibility of race conditions causing stale data
        # to be saved:

        Asset.objects.bulk_update(asset_chunk, ["storage_image"])
        updated_count += len(asset_chunk)

        logger.debug("Storage image updated count %s", updated_count)

    return updated_count, storage_image_empty_count


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
def create_elasticsearch_indices():
    call_command("search_index", action="create")


@celery_app.task
def populate_elasticsearch_indices():
    call_command("search_index", action="populate")


@celery_app.task
def delete_elasticsearch_indices():
    call_command("search_index", "-f", action="delete")


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
        now = timezone.now()
        ONE_DAY_AGO = now - datetime.timedelta(days=1)
        context = {
            "title": "Unusual User Activity Report for "
            + now.strftime("%b %d %Y, %I:%M %p"),
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


@celery_app.task(ignore_result=True)
def update_from_cache():
    for key in cache.keys("userprofileactivity_*"):
        _, user_id, campaign_id, field = key.split("_")
        value = cache.get(key)
        update_userprofileactivity_table(user_id, campaign_id, field, value)
        cache.delete(key)
