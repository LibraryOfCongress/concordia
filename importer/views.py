import os
import shutil
import boto3
import botocore
from logging import getLogger

from celery.result import AsyncResult
from django.conf import settings
from django.shortcuts import redirect
from django.template.defaultfilters import slugify
from django.urls import reverse
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from concordia.models import Asset, Campaign, Item, Project
from importer.models import CampaignItemAssetCount, CampaignTaskDetails
from importer.serializer import CreateCampaign
from importer.tasks import (download_write_campaign_item_assets,
                            download_write_item_assets, get_item_id_from_item_url)
from importer.config import IMPORTER

logger = getLogger(__name__)

S3_CLIENT = boto3.client("s3")
S3_BUCKET_NAME = IMPORTER.get("S3_BUCKET_NAME", "")
S3_RESOURCE = boto3.resource("s3")


class CreateCampaignView(generics.CreateAPIView):
    serializer_class = CreateCampaign

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.data
        name = data.get("name")
        project = data.get("project")
        url = data.get("url")
        create_type = data.get("create_type")
        campaign_details = {
            "campaign_name": name,
            "campaign_slug": slugify(name),
            "project_name": project,
            "project_slug": slugify(project),
        }

        if create_type == "campaigns":

            download_task = download_write_campaign_item_assets.delay(
                slugify(name), slugify(project), url
            )
            campaign_details["campaign_task_id"] = download_task.task_id
            CampaignTaskDetails.objects.create(**campaign_details)
            data["task_id"] = download_task.task_id

        elif create_type == "item":
            item_id = get_item_id_from_item_url(url)
            download_task = download_write_item_assets.delay(
                slugify(name), slugify(project), item_id
            )
            ctd, created = CampaignTaskDetails.objects.get_or_create(
                campaign_slug=slugify(name),
                project_slug=slugify(project),
                defaults={"campaign_name": name, "project_name": project},
            )
            CampaignItemAssetCount.objects.create(
                campaign_task=ctd,
                campaign_item_identifier=item_id,
                item_task_id=download_task.task_id,
            )

            data["task_id"] = download_task.task_id
            data["item_id"] = item_id

        headers = self.get_success_headers(data)
        return Response(data, status=status.HTTP_202_ACCEPTED, headers=headers)


@api_view(["GET"])
def get_task_status(request, task_id):

    if request.method == "GET":
        celery_task_result = AsyncResult(task_id)
        task_state = celery_task_result.state

        try:
            ciac = CampaignItemAssetCount.objects.get(item_task_id=task_id)
            project_local_path = os.path.join(
                settings.IMPORTER["IMAGES_FOLDER"],
                ciac.campaign_task.campaign_slug,
                ciac.campaign_task.project_slug,
            )
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
                    ctd.campaign_slug,
                    ctd.project_slug,
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
            # return Response({"message": "Requested task id Does not exists for item progress"},
            #                 status.HTTP_404_NOT_FOUND)

        # return Response(task_state)


def check_completeness(ciac, item_id=None):

    project_local_path = os.path.join(
        settings.IMPORTER["IMAGES_FOLDER"],
        ciac.campaign_task.campaign_slug,
        ciac.campaign_task.project_slug,
    )
    if item_id:
        item_local_path = os.path.join(project_local_path, item_id)
        item_downloaded_asset_count = sum(
            [len(files) for path, dirs, files in os.walk(item_local_path)]
        )
        if ciac.campaign_item_asset_count == item_downloaded_asset_count:
            return True
        else:
            shutil.rmtree(item_local_path)
            CampaignTaskDetails.objects.get(
                campaign_slug=ciac.campaign_task.campaign_slug
            ).delete()
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
            CampaignTaskDetails.objects.get(
                campaign_slug=ciac.campaign_task.campaign_slug
            ).delete()
            return False
    return False


def save_campaign_item_assets(project, item, the_path, item_id=None):
    list_asset_info = []

    for root, dirs, files in os.walk(the_path):
        for filename in files:
            file_path = os.path.join(root, filename)
            if item_id:
                title = item_id
            else:
                title = file_path.replace(the_path + "/", "").split("/")[0]

            media_url = file_path.replace(settings.IMPORTER["IMAGES_FOLDER"], "")
            sequence = int(os.path.splitext(filename)[0])
            asset_info = Asset(
                title=title,
                slug="{0}{1}".format(title, sequence),
                description="{0} description".format(title),
                media_url=media_url,
                media_type="IMG",
                sequence=sequence,
                campaign=project.campaign,
                project=project,
                item=item,
            )
            list_asset_info.append(asset_info)
            try:
                item_path = "/".join(
                    os.path.join(settings.MEDIA_ROOT, media_url).split("/")[:-1]
                )
                os.makedirs(item_path)
            except Exception as e:
                logger.error("Error/warning while creating dir path: %s" % e)
            # Asset.objects.create(
            #     title=title,
            #     slug="{0}{1}".format(title, sequence),
            #     description="{0} description".format(title),
            #     media_url=media_url,
            #     media_type="IMG",
            #     sequence=sequence,
            #     campaign=project.campaign,
            #     project=project,
            #     item=item,
            # )
    Asset.objects.bulk_create(list_asset_info)
    if S3_BUCKET_NAME:
        for a in list_asset_info:
            try:
                source_file_path = os.path.join(settings.IMPORTER["IMAGES_FOLDER"], a.media_url)
                S3_CLIENT.upload_file(source_file_path, S3_BUCKET_NAME, a.media_url)
                logger.info(
                    "Uploaded %(filename)s to %(bucket_name)s",
                    {"filename": source_file_path, "bucket_name": S3_BUCKET_NAME},
                )
            except:
                logger.info(
                    "Files in %(filename)s already exists in s3 bucket",
                    {"filename": source_file_path},
                )
    else:
        shutil.move(the_path, os.path.join(settings.MEDIA_ROOT, the_path.replace(settings.IMPORTER["IMAGES_FOLDER"], "")))        

def check_image_file_on_s3(filename, filesize):
    if S3_BUCKET_NAME:
        try:
            object_summary = S3_RESOURCE.ObjectSummary(S3_BUCKET_NAME, filename)
            if object_summary.size == filesize:
                return True
            else:
                return False
        except botocore.exceptions.ClientError:
            return False
    else:
        return False

@api_view(["GET"])
def check_and_save_campaign_assets(request, task_id, item_id=None):

    if request.method == "GET":
        logger.info("check_and_save_campaign_assets for item_id: ", item_id)

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
                        "transcriptions:project",
                        args=[
                            ciac.campaign_task.campaign_slug,
                            ciac.campaign_task.project_slug,
                        ],
                        current_app=request.resolver_match.namespace,
                    )
                )
        else:
            try:
                ctd = CampaignTaskDetails.objects.get(campaign_task_id=task_id)
                ciac = CampaignItemAssetCount.objects.filter(campaign_task=ctd)[0]
            except CampaignTaskDetails.DoesNotExist:
                return Response(
                    {"message": "Requested Campaign Does not exists"},
                    status.HTTP_404_NOT_FOUND,
                )
            if check_and_save_campaign_completeness(ciac):
                return redirect(
                    reverse(
                        "transcriptions:campaign",
                        args=[ctd.campaign_slug],
                        current_app=request.resolver_match.namespace,
                    )
                )
        return Response(
            {
                "message": "Creating a campaign is failed since assets are not completely downloaded"
            },
            status=status.HTTP_404_NOT_FOUND,
        )


def check_and_save_campaign_completeness(ciac):
    if check_completeness(ciac):
        try:
            project = Project.objects.get(
                campaign__slug=ciac.campaign_task.campaign_slug,
                slug=ciac.campaign_task.project_slug,
            )
        except Project.DoesNotExist:
            campaign, created = Campaign.objects.get_or_create(
                title=ciac.campaign_task.campaign_name,
                slug=ciac.campaign_task.campaign_slug,
                description=ciac.campaign_task.campaign_name,
                is_active=True,
            )

            project = Project.objects.create(
                title=ciac.campaign_task.project_name,
                campaign=campaign,
                slug=ciac.campaign_task.project_slug,
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


def check_and_save_item_completeness(ciac, item_id):

    if check_completeness(ciac, item_id):
        campaign, created = Campaign.objects.get_or_create(
            title=ciac.campaign_task.campaign_name,
            slug=ciac.campaign_task.campaign_slug,
            description=ciac.campaign_task.campaign_name,
            is_active=True,
        )

        try:
            project = Project.objects.get(
                campaign__slug=ciac.campaign_task.campaign_slug,
                slug=ciac.campaign_task.project_slug,
            )
        except Project.DoesNotExist:

            project = Project.objects.create(
                title=ciac.campaign_task.project_name,
                campaign=campaign,
                slug=ciac.campaign_task.project_slug,
            )

        try:
            item = Item.objects.get(
                campaign__slug=ciac.campaign_task.campaign_slug,
                project__slug=ciac.campaign_task.project_slug,
                title=item_id,
                slug=item_id,
                item_id=item_id,
            )
        except Item.DoesNotExist:
            item = Item.objects.create(
                campaign=campaign,
                project=project,
                item_id=item_id,
                title=item_id,
                slug=item_id,
            )

        item_local_path = os.path.join(
            settings.IMPORTER["IMAGES_FOLDER"],
            project.campaign.slug,
            project.slug,
            item_id,
        )

        save_campaign_item_assets(project, item, item_local_path, item_id)
        shutil.rmtree(
            os.path.join(
                settings.IMPORTER["IMAGES_FOLDER"], project.campaign.slug, project.slug
            )
        )
        return True

    return False
