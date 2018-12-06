from logging import getLogger

from celery import task
from django.contrib.auth.models import User
from django.db.models import Count

from concordia.models import (
    Asset,
    Campaign,
    Item,
    Project,
    SiteReport,
    Tag,
    Transcription,
    UserAssetTagCollection,
)
from concordia.utils import get_anonymous_user

logger = getLogger(__name__)


@task
def site_report():

    report = dict()
    report["assets_not_started"] = 0
    report["assets_in_progress"] = 0
    report["assets_submitted"] = 0
    report["assets_completed"] = 0

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

    tag_collections = UserAssetTagCollection.objects.all()
    tag_count = 0
    distinct_tag_count = Tag.objects.all().count()

    for tag_group in tag_collections:
        tag_count += tag_group.tags.count()

    site_report = SiteReport()
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
    site_report.distinct_tags = distinct_tag_count
    site_report.tag_uses = tag_count
    site_report.campaigns_published = campaigns_published
    site_report.campaigns_unpublished = campaigns_unpublished
    site_report.users_registered = users_registered
    site_report.users_activated = users_activated
    site_report.save()

    for campaign in Campaign.objects.all():
        campaign_report(campaign)


def campaign_report(campaign):

    report = dict()
    report["assets_not_started"] = 0
    report["assets_in_progress"] = 0
    report["assets_submitted"] = 0
    report["assets_completed"] = 0
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
        Item.objects.published().filter(project__campaign=campaign).count()
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

    asset_tag_collections = UserAssetTagCollection.objects.filter(
        asset__item__project__campaign=campaign
    )
    tag_count = 0
    distinct_tag_list = set()

    for tag_collection in asset_tag_collections:
        tag_count += tag_collection.tags.all().count()
        distinct_tag_list.add(tag_collection.tags.all())

    distinct_tag_count = len(distinct_tag_list)

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
    site_report.distinct_tags = distinct_tag_count
    site_report.tag_uses = tag_count
    site_report.save()
