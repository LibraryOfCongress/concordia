from logging import getLogger

from django.contrib.auth.models import User
from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from concordia.logging import ConcordiaLogger
from concordia.models import (
    ONE_DAY_AGO,
    Asset,
    Campaign,
    Item,
    Project,
    SiteReport,
    Tag,
    Topic,
    Transcription,
    UserAssetTagCollection,
)
from concordia.utils import get_anonymous_user

from ...celery import app as celery_app

logger = getLogger(__name__)
structured_logger = ConcordiaLogger.get_logger(__name__)


def _recent_transcriptions() -> QuerySet[Transcription]:
    """
    Return transcriptions with activity in the last day.

    "Recent" activity is defined as any transcription whose accepted, created,
    rejected, submitted, or updated timestamp is greater than or equal to
    ONE_DAY_AGO. This queryset is used as the basis for daily activity and DAU
    calculations.

    Returns:
        QuerySet[Transcription]: Django queryset of recent transcriptions.
    """
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


def _daily_active_users() -> int:
    """
    Calculate the daily active user count based on recent transcriptions.

    A daily active user is any account that either created or updated a
    transcription, or performed a review, within the last day.

    Returns:
        int: The number of unique users who were active in the last day.
    """
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
def site_report() -> None:
    """
    Generate site-wide, per-campaign, per-topic, and retired rollup SiteReports.

    This task snapshots current counts for assets, items, projects, campaigns,
    tags, users, and transcription activity into SiteReport rows. It creates a
    site-wide TOTAL report, then per-campaign and per-topic reports, and
    finally a RETIRED_TOTAL rollup for retired campaigns.

    For per-campaign and per-topic reports, the ``assets_started`` metric is
    derived from ``assets_total`` and ``assets_not_started``, so
    publish/unpublish changes alone do not affect the calculated starts as
    long as total and not-started counts remain consistent.

    For the site-wide TOTAL report, ``assets_started`` is calculated by rolling
    up the per-campaign ``assets_started`` values generated in the same daily
    reporting run. This avoids confounding changes to the site-wide series
    caused by campaign retirements.

    The RETIRED_TOTAL rollup does not calculate ``assets_started``; it is set
    to zero because membership changes when campaigns retire, and the daily
    delta is not meaningful for that rollup.
    """
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

    site_report = SiteReport()
    site_report.report_name = SiteReport.ReportName.TOTAL
    site_report.assets_total = assets_total
    site_report.assets_published = assets_published
    site_report.assets_not_started = report["assets_not_started"]
    site_report.assets_in_progress = report["assets_in_progress"]
    site_report.assets_waiting_review = report["assets_submitted"]
    site_report.assets_completed = report["assets_completed"]
    site_report.assets_unpublished = assets_unpublished
    site_report.assets_started = 0
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
        assets_started=site_report.assets_started,
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
    campaign_reports = []
    for campaign in campaigns:
        campaign_reports.append(campaign_report(campaign))
    structured_logger.debug(
        "Campaign reports generation completed.",
        event_code="campaign_reports_generation_complete",
    )

    total_assets_started = sum(
        (campaign_site_report.assets_started or 0)
        for campaign_site_report in campaign_reports
        if campaign_site_report is not None
    )
    if site_report.assets_started != total_assets_started:
        site_report.assets_started = total_assets_started
        site_report.save(update_fields=["assets_started"])

        structured_logger.debug(
            "Site-wide assets_started rolled up from campaign reports.",
            event_code="site_report_assets_started_rolled_up",
            site_report_id=site_report.id,
            created_on=site_report.created_on.isoformat(),
            assets_started=total_assets_started,
            campaign_report_count=len(campaign_reports),
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


def topic_report(topic: Topic) -> None:
    """
    Generate and save a SiteReport snapshot for a single topic.

    The report aggregates asset, item, project, tag, and review activity counts
    for the topic and stores them as a new SiteReport row.

    Args:
        topic: Topic instance to generate a report for.
    """
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
        previous_assets_total=getattr(previous, "assets_total", 0),
        previous_assets_not_started=getattr(previous, "assets_not_started", 0),
        current_assets_total=assets_total,
        current_assets_not_started=report["assets_not_started"],
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


def campaign_report(campaign: Campaign) -> SiteReport:
    """
    Generate and save a SiteReport snapshot for a single campaign.

    The report aggregates asset, item, project, contributor, tag, and review
    counts for the campaign and stores them as a new SiteReport row.

    The ``assets_started`` metric is derived from ``assets_total`` and
    ``assets_not_started``, so publish/unpublish changes alone do not affect
    the calculated starts as long as total and not-started counts remain
    consistent.

    Args:
        campaign: Campaign instance to generate a report for.

    Returns:
        SiteReport: The newly created campaign SiteReport.
    """
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
        previous_assets_total=getattr(previous, "assets_total", 0),
        previous_assets_not_started=getattr(previous, "assets_not_started", 0),
        current_assets_total=assets_total,
        current_assets_not_started=report["assets_not_started"],
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
    return site_report


def retired_total_report() -> None:
    """
    Generate and save the RETIRED_TOTAL SiteReport rollup.

    This aggregates the most recent SiteReport for each retired campaign into a
    single rollup row, summing most fields directly.

    assets_started is a daily-delta metric and is not meaningful for this
    rollup because the rollup membership changes when campaigns retire, and
    that causes every asset in a newly-retired campaign being counted
    as having started on the day of the retirement.
    """
    structured_logger.debug(
        "Starting retired total report generation.",
        event_code="retired_total_report_generation_start",
    )
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

    for field in FIELDS:
        setattr(
            total_site_report,
            field,
            sum(getattr(sr, field) or 0 for sr in site_reports),
        )

    # assets_started will always be zero for retired campaigns,
    # since no assets could ever be started once a campaign is
    # retired. Trying to calculate it like we do for other reports
    # results in every single asset from a newly retired campaign
    # being counted as having started
    total_site_report.assets_started = 0

    total_site_report.save()
    structured_logger.debug(
        "Retired total report saved successfully.",
        event_code="retired_total_report_saved",
        site_report_id=total_site_report.id,
        created_on=total_site_report.created_on.isoformat(),
    )
