from celery import task
from django.contrib.auth.models import User

from concordia.models import (
    Asset,
    Campaign,
    Item,
    Project,
    SiteReport,
    Tag,
    Transcription,
    TranscriptionStatus,
    UserAssetTagCollection,
)


@task
def site_report():
    assets_total = Asset.objects.count()
    assets_published = Asset.objects.filter(published=True).count()
    assets_not_started = Asset.objects.filter(
        transcription_status=TranscriptionStatus.NOT_STARTED
    ).count()
    assets_in_progress = Asset.objects.filter(
        transcription_status=TranscriptionStatus.IN_PROGRESS
    ).count()
    assets_waiting_review = Asset.objects.filter(
        transcription_status=TranscriptionStatus.SUBMITTED
    ).count()
    assets_completed = Asset.objects.filter(
        transcription_status=TranscriptionStatus.COMPLETED
    ).count()
    assets_unpublished = Asset.objects.filter(published=False).count()

    items_published = Item.objects.filter(published=True).count()
    items_unpublished = Item.objects.filter(published=False).count()

    projects_published = Project.objects.filter(published=True).count()
    projects_unpublished = Project.objects.filter(published=False).count()

    campaigns_published = Campaign.objects.filter(published=True).count()
    campaigns_unpublished = Campaign.objects.filter(published=False).count()

    users_registered = User.objects.all().count()
    users_activated = User.objects.filter(is_active=True).count()

    anonymous_transcriptions = Transcription.objects.filter(
        user__username="anonymous"
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
    site_report.assets_not_started = assets_not_started
    site_report.assets_in_progress = assets_in_progress
    site_report.assets_waiting_review = assets_waiting_review
    site_report.assets_completed = assets_completed
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

    assets_total = Asset.objects.filter(item__project__campaign=campaign).count()
    assets_published = Asset.objects.filter(
        item__project__campaign=campaign, published=True
    ).count()
    assets_not_started = Asset.objects.filter(
        item__project__campaign=campaign,
        transcription_status=TranscriptionStatus.NOT_STARTED,
    ).count()
    assets_in_progress = Asset.objects.filter(
        item__project__campaign=campaign,
        transcription_status=TranscriptionStatus.IN_PROGRESS,
    ).count()
    assets_waiting_review = Asset.objects.filter(
        item__project__campaign=campaign,
        transcription_status=TranscriptionStatus.SUBMITTED,
    ).count()
    assets_completed = Asset.objects.filter(
        item__project__campaign=campaign,
        transcription_status=TranscriptionStatus.COMPLETED,
    ).count()
    assets_unpublished = Asset.objects.filter(
        item__project__campaign=campaign, published=False
    ).count()

    items_published = Item.objects.filter(
        project__campaign=campaign, published=True
    ).count()
    items_unpublished = Item.objects.filter(
        project__campaign=campaign, published=False
    ).count()

    projects_published = Project.objects.filter(
        campaign=campaign, published=True
    ).count()
    projects_unpublished = Project.objects.filter(
        campaign=campaign, published=False
    ).count()

    anonymous_transcriptions = Transcription.objects.filter(
        asset__item__project__campaign=campaign, user__username="anonymous"
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
    site_report.assets_not_started = assets_not_started
    site_report.assets_in_progress = assets_in_progress
    site_report.assets_waiting_review = assets_waiting_review
    site_report.assets_completed = assets_completed
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
