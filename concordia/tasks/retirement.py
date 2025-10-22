from logging import getLogger

from celery import chord
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from concordia.logging import ConcordiaLogger
from concordia.models import Asset, Campaign, CampaignRetirementProgress, Item, Project

from ..celery import app as celery_app

logger = getLogger(__name__)
structured_logger = ConcordiaLogger.get_logger(__name__)


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
