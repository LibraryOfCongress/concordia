from logging import getLogger

from celery import task
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db.models import Count
from more_itertools.more import chunked

from concordia.models import (
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

logger = getLogger(__name__)


@task
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

    stats = UserAssetTagCollection.objects.aggregate(Count("tags"))
    tag_count = stats["tags__count"]

    distinct_tag_count = Tag.objects.all().count()

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

    for topic in Topic.objects.all():
        topic_report(topic)


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

    asset_tag_collections = UserAssetTagCollection.objects.filter(
        asset__item__project__topics=topic
    )

    stats = asset_tag_collections.order_by().aggregate(tag_count=Count("tags"))
    tag_count = stats["tag_count"]

    distinct_tag_list = set()

    for tag_collection in asset_tag_collections:
        distinct_tag_list.add(tag_collection.tags.values_list("pk", flat=True))

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

    stats = asset_tag_collections.order_by().aggregate(tag_count=Count("tags"))
    tag_count = stats["tag_count"]

    distinct_tag_list = set()

    for tag_collection in asset_tag_collections:
        distinct_tag_list.add(tag_collection.tags.values_list("pk", flat=True))

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


@task
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


@task
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


@task
def create_elasticsearch_indices():
    call_command("search_index", action="create")


@task
def populate_elasticsearch_indices():
    call_command("search_index", action="populate")


@task
def delete_elasticsearch_indices():
    call_command("search_index", "-f", action="delete")
