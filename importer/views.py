import os
import shutil
from logging import getLogger

import boto3
from celery.result import AsyncResult
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from concordia.models import Asset, Campaign, Item, Project
from importer.models import CampaignItemAssetCount, CampaignTaskDetails

logger = getLogger(__name__)

S3_CLIENT = boto3.client("s3")
S3_BUCKET_NAME = settings.AWS_S3.get("S3_COLLECTION_BUCKET", "")
S3_RESOURCE = boto3.resource("s3")


@api_view(["GET"])
def get_task_status(request, task_id):
    celery_task_result = AsyncResult(task_id)
    task_state = celery_task_result.state

    try:
        ciac = CampaignItemAssetCount.objects.get(item_task_id=task_id)
        project_local_path = os.path.join(
            settings.IMPORTER["IMAGES_FOLDER"],
            ciac.campaign_task.project.campaign.slug,
            ciac.campaign_task.project.slug,
        )

        # FIXME: why don't we trust our records?
        item_downloaded_asset_count = sum(
            [
                len(files)
                for path, dirs, files in os.walk(
                    os.path.join(project_local_path, ciac.campaign_item_identifier)
                )
            ]
        )
        if item_downloaded_asset_count <= ciac.campaign_item_asset_count:
            progress = "%s of %s processed" % (
                item_downloaded_asset_count,
                ciac.campaign_item_asset_count,
            )
        else:
            progress = ""
        return Response({"state": task_state, "progress": progress})
    except CampaignItemAssetCount.DoesNotExist:
        try:
            ctd = CampaignTaskDetails.objects.get(campaign_task_id=task_id)
            project_local_path = os.path.join(
                settings.IMPORTER["IMAGES_FOLDER"],
                ctd.project.campaign.slug,
                ctd.project.slug,
            )
            campaign_downloaded_asset_count = sum(
                [len(files) for path, dirs, files in os.walk(project_local_path)]
            )
            if campaign_downloaded_asset_count <= ctd.campaign_asset_count:
                progress = "%s of %s processed" % (
                    campaign_downloaded_asset_count,
                    ctd.campaign_asset_count,
                )
            else:
                progress = ""
            return Response({"state": task_state, "progress": progress})
        except CampaignTaskDetails.DoesNotExist:
            return Response(
                {"message": "Requested task id Does not exists campaign progress"},
                status.HTTP_404_NOT_FOUND,
            )


def check_completeness(ciac, item_id=None):

    project_local_path = os.path.join(
        settings.IMPORTER["IMAGES_FOLDER"],
        ciac.campaign_task.project.campaign.slug,
        ciac.campaign_task.project.slug,
    )
    if item_id:
        item_local_path = os.path.join(project_local_path, item_id)
        item_downloaded_asset_count = sum(
            [len(files) for path, dirs, files in os.walk(item_local_path)]
        )

        if ciac.campaign_item_asset_count == item_downloaded_asset_count:
            return True
        else:
            raise NotImplementedError()
            shutil.rmtree(item_local_path)
            return False

    else:
        campaign_items = os.listdir(project_local_path)
        campaign_downloaded_item_count = len(campaign_items)
        campaign_downloaded_asset_count = sum(
            [len(files) for path, dirs, files in os.walk(project_local_path)]
        )
        if (
            campaign_downloaded_asset_count == ciac.campaign_task.campaign_asset_count
        ) and (
            campaign_downloaded_item_count == ciac.campaign_task.campaign_item_count
        ):
            return True
        else:
            shutil.rmtree(project_local_path)
            raise NotImplementedError()
            return False
    return False


def save_campaign_item_assets(project, the_path, item_id=None):
    list_asset_info = []

    for root, dirs, files in os.walk(the_path):
        for filename in files:
            file_path = os.path.join(root, filename)
            if item_id:
                title = item_id
            else:
                title = file_path.replace(the_path + "/", "").split("/")[0]

            media_url = os.path.relpath(file_path, settings.IMPORTER["IMAGES_FOLDER"])
            sequence = int(os.path.splitext(filename)[0])

            item = project.item_set.get(item_id=title)

            asset_info = Asset(
                title=title,
                slug="{0}—{1}".format(title, sequence),
                description="{0} description".format(title),
                media_url=media_url,
                media_type="IMG",
                sequence=sequence,
                campaign=project.campaign,
                project=project,
                item=item,
            )

            list_asset_info.append(asset_info)

            item_path = "/".join(
                os.path.join(settings.MEDIA_ROOT, media_url).split("/")[:-1]
            )

            os.makedirs(item_path, exist_ok=True)

    Asset.objects.bulk_create(list_asset_info)

    for a in list_asset_info:
        source_file_path = os.path.join(settings.IMPORTER["IMAGES_FOLDER"], a.media_url)

        if S3_BUCKET_NAME:
            try:
                S3_CLIENT.upload_file(source_file_path, S3_BUCKET_NAME, a.media_url)
                logger.info(
                    "Uploaded %(filename)s to %(bucket_name)s",
                    {"filename": source_file_path, "bucket_name": S3_BUCKET_NAME},
                )
            except Exception:
                # FIXME: this needs to handle all other exception types!
                logger.error(
                    "Files in %(filename)s already exists in s3 bucket",
                    {"filename": source_file_path},
                    exc_info=True,
                )
                raise
        else:
            shutil.move(
                source_file_path, os.path.join(settings.MEDIA_ROOT, a.media_url)
            )


@api_view(http_method_names=["GET"])
def check_and_save_campaign_assets(request, task_id, item_id=None):
    logger.debug("check_and_save_campaign_assets for item_id %s", item_id)

    if item_id:
        try:
            ciac = CampaignItemAssetCount.objects.get(
                item_task_id=task_id, campaign_item_identifier=item_id
            )
        except CampaignItemAssetCount.DoesNotExist:
            return Response(
                {"message": "Requested Campaign Does not exists"},
                status.HTTP_404_NOT_FOUND,
            )

        if check_and_save_item_completeness(ciac, item_id):
            return redirect(
                reverse(
                    "transcriptions:project-detail",
                    args=[
                        ciac.campaign_task.project.campaign.slug,
                        ciac.campaign_task.project.slug,
                    ],
                    current_app=request.resolver_match.namespace,
                )
            )
    else:
        try:
            ctd = CampaignTaskDetails.objects.get(campaign_task_id=task_id)
        except CampaignTaskDetails.DoesNotExist:
            return Response(
                {"message": "Requested Campaign Does not exists"},
                status.HTTP_404_NOT_FOUND,
            )

        # FIXME: determine what we're doing with n > 1
        ciac = CampaignItemAssetCount.objects.filter(campaign_task=ctd)[0]

        if check_and_save_campaign_completeness(ciac):
            return redirect(
                reverse(
                    "transcriptions:campaign",
                    args=[ctd.project.campaign.slug],
                    current_app=request.resolver_match.namespace,
                )
            )

    return Response(
        # FIXME: we need better error reporting
        {"message": "Unable to determine what failed"},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def check_and_save_campaign_completeness(ciac):
    if check_completeness(ciac):
        try:
            project = Project.objects.get(
                campaign__slug=ciac.campaign_task.campaign_slug,
                slug=ciac.campaign_task.project.slug,
            )
        except Project.DoesNotExist:
            if S3_BUCKET_NAME:
                s3_storage = True
            else:
                s3_storage = False
            campaign, created = Campaign.objects.get_or_create(
                title=ciac.campaign_task.campaign_name,
                slug=ciac.campaign_task.campaign_slug,
                description=ciac.campaign_task.campaign_name,
                is_active=True,
                s3_storage=s3_storage,
            )

            project = Project.objects.create(
                title=ciac.campaign_task.project_name,
                campaign=campaign,
                slug=ciac.campaign_task.project.slug,
            )

        project_local_path = os.path.join(
            settings.IMPORTER["IMAGES_FOLDER"], project.campaign.slug, project.slug
        )

        save_campaign_item_assets(project, project_local_path)

        shutil.rmtree(
            os.path.join(
                settings.IMPORTER["IMAGES_FOLDER"], project.campaign.slug, project.slug
            )
        )

        return True

    return False
