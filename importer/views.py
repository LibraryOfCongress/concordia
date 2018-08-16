import os
import shutil
from logging import getLogger

from celery.result import AsyncResult
from django.conf import settings
from django.shortcuts import redirect
from django.template.defaultfilters import slugify
from django.urls import reverse
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from concordia.models import Asset, Collection, Subcollection
from importer.models import CollectionItemAssetCount, CollectionTaskDetails
from importer.serializer import CreateCollection
from importer.tasks import (download_write_collection_item_assets,
                            download_write_item_assets, get_item_id_from_item_url)

logger = getLogger(__name__)


class CreateCollectionView(generics.CreateAPIView):
    serializer_class = CreateCollection

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.data
        name = data.get("name")
        project = data.get("project")
        url = data.get("url")
        create_type = data.get("create_type")
        collection_details = {
            "collection_name": name,
            "collection_slug": slugify(name),
            "subcollection_name": project,
            "subcollection_slug": slugify(project),
        }

        if create_type == "collections":

            download_task = download_write_collection_item_assets.delay(
                slugify(name), slugify(project), url
            )
            collection_details["collection_task_id"] = download_task.task_id
            CollectionTaskDetails.objects.create(**collection_details)
            data["task_id"] = download_task.task_id

        elif create_type == "item":
            item_id = get_item_id_from_item_url(url)
            download_task = download_write_item_assets.delay(
                slugify(name), slugify(project), item_id
            )
            ctd, created = CollectionTaskDetails.objects.get_or_create(
                collection_slug=slugify(name),
                subcollection_slug=slugify(project),
                defaults={"collection_name": name, "subcollection_name": project},
            )
            CollectionItemAssetCount.objects.create(
                collection_task=ctd,
                collection_item_identifier=item_id,
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
            ciac = CollectionItemAssetCount.objects.get(item_task_id=task_id)
            project_local_path = os.path.join(
                settings.IMPORTER["IMAGES_FOLDER"],
                ciac.collection_task.collection_slug,
                ciac.collection_task.subcollection_slug,
            )
            item_downloaded_asset_count = sum(
                [
                    len(files)
                    for path, dirs, files in os.walk(
                        os.path.join(
                            project_local_path, ciac.collection_item_identifier
                        )
                    )
                ]
            )
            if item_downloaded_asset_count <= ciac.collection_item_asset_count:
                progress = "%s of %s processed" % (
                    item_downloaded_asset_count,
                    ciac.collection_item_asset_count,
                )
            else:
                progress = ""
            return Response({"state": task_state, "progress": progress})
        except CollectionItemAssetCount.DoesNotExist:
            try:
                ctd = CollectionTaskDetails.objects.get(collection_task_id=task_id)
                project_local_path = os.path.join(
                    settings.IMPORTER["IMAGES_FOLDER"],
                    ctd.collection_slug,
                    ctd.subcollection_slug,
                )
                collection_downloaded_asset_count = sum(
                    [len(files) for path, dirs, files in os.walk(project_local_path)]
                )
                if collection_downloaded_asset_count <= ctd.collection_asset_count:
                    progress = "%s of %s processed" % (
                        collection_downloaded_asset_count,
                        ctd.collection_asset_count,
                    )
                else:
                    progress = ""
                return Response({"state": task_state, "progress": progress})
            except CollectionTaskDetails.DoesNotExist:
                return Response(
                    {
                        "message": "Requested task id Does not exists collection progress"
                    },
                    status.HTTP_404_NOT_FOUND,
                )
            # return Response({"message": "Requested task id Does not exists for item progress"},
            #                 status.HTTP_404_NOT_FOUND)

        # return Response(task_state)


def check_completeness(ciac, item_id=None):

    project_local_path = os.path.join(
        settings.IMPORTER["IMAGES_FOLDER"],
        ciac.collection_task.collection_slug,
        ciac.collection_task.subcollection_slug,
    )
    if item_id:
        item_local_path = os.path.join(project_local_path, item_id)
        item_downloaded_asset_count = sum(
            [len(files) for path, dirs, files in os.walk(item_local_path)]
        )
        if ciac.collection_item_asset_count == item_downloaded_asset_count:
            return True
        else:
            shutil.rmtree(item_local_path)
            CollectionTaskDetails.objects.get(
                collection_slug=ciac.collection_task.collection_slug
            ).delete()
            return False

    else:
        collection_items = os.listdir(project_local_path)
        collection_downloaded_item_count = len(collection_items)
        collection_downloaded_asset_count = sum(
            [len(files) for path, dirs, files in os.walk(project_local_path)]
        )
        if (
            collection_downloaded_asset_count
            == ciac.collection_task.collection_asset_count
        ) and (
            collection_downloaded_item_count
            == ciac.collection_task.collection_item_count
        ):
            return True
        else:
            shutil.rmtree(project_local_path)
            CollectionTaskDetails.objects.get(
                collection_slug=ciac.collection_task.collection_slug
            ).delete()
            return False
    return False


def save_collection_item_assets(subcollection, the_path, item_id=None):

    for root, dirs, files in os.walk(the_path):
        for filename in files:
            file_path = os.path.join(root, filename)
            if item_id:
                title = item_id
            else:
                title = file_path.replace(the_path + "/", "").split("/")[0]
            media_url = file_path.replace(settings.IMPORTER["IMAGES_FOLDER"], "")
            sequence = int(os.path.splitext(filename)[0])
            Asset.objects.create(
                title=title,
                slug="{0}{1}".format(title, sequence),
                description="{0} description".format(title),
                media_url=media_url,
                media_type="IMG",
                sequence=sequence,
                collection=subcollection.collection,
                subcollection=subcollection,
            )

            try:
                item_path = "/".join(
                    os.path.join(settings.MEDIA_ROOT, media_url).split("/")[:-1]
                )
                os.makedirs(item_path)
            except Exception as e:
                logger.error("Error/warning while creating dir path: %s" % e)

            shutil.move(file_path, os.path.join(settings.MEDIA_ROOT, media_url))


@api_view(["GET"])
def check_and_save_collection_assets(request, task_id, item_id=None):

    if request.method == "GET":
        logger.info("check_and_save_collection_assets for item_id: ", item_id)

        if item_id:
            try:
                ciac = CollectionItemAssetCount.objects.get(
                    item_task_id=task_id, collection_item_identifier=item_id
                )
            except CollectionItemAssetCount.DoesNotExist:
                return Response(
                    {"message": "Requested Collection Does not exists"},
                    status.HTTP_404_NOT_FOUND,
                )
            if check_and_save_item_completeness(ciac, item_id):
                return redirect(
                    reverse(
                        "transcriptions:project",
                        args=[
                            ciac.collection_task.collection_slug,
                            ciac.collection_task.subcollection_slug,
                        ],
                        current_app=request.resolver_match.namespace,
                    )
                )
        else:
            try:
                ctd = CollectionTaskDetails.objects.get(collection_task_id=task_id)
                ciac = CollectionItemAssetCount.objects.filter(collection_task=ctd)[0]
            except CollectionTaskDetails.DoesNotExist:
                return Response(
                    {"message": "Requested Collection Does not exists"},
                    status.HTTP_404_NOT_FOUND,
                )
            if check_and_save_collection_completeness(ciac):
                return redirect(
                    reverse(
                        "transcriptions:collection",
                        args=[ctd.collection_slug],
                        current_app=request.resolver_match.namespace,
                    )
                )
        return Response(
            {
                "message": "Creating a collection is failed since assets are not completely downloaded"
            },
            status=status.HTTP_404_NOT_FOUND,
        )


def check_and_save_collection_completeness(ciac):
    if check_completeness(ciac):
        try:
            subcollection = Subcollection.objects.get(
                collection__slug=ciac.collection_task.collection_slug,
                slug=ciac.collection_task.subcollection_slug,
            )
        except Subcollection.DoesNotExist:
            collection, created = Collection.objects.get_or_create(
                title=ciac.collection_task.collection_name,
                slug=ciac.collection_task.collection_slug,
                description=ciac.collection_task.collection_name,
                is_active=True,
            )

            subcollection = Subcollection.objects.create(
                title=ciac.collection_task.subcollection_name,
                collection=collection,
                slug=ciac.collection_task.subcollection_slug,
            )

        project_local_path = os.path.join(
            settings.IMPORTER["IMAGES_FOLDER"],
            subcollection.collection.slug,
            subcollection.slug,
        )

        save_collection_item_assets(subcollection, project_local_path)

        shutil.rmtree(
            os.path.join(
                settings.IMPORTER["IMAGES_FOLDER"],
                subcollection.collection.slug,
                subcollection.slug,
            )
        )

        return True

    return False


def check_and_save_item_completeness(ciac, item_id):

    if check_completeness(ciac, item_id):
        try:
            subcollection = Subcollection.objects.get(
                collection__slug=ciac.collection_task.collection_slug,
                slug=ciac.collection_task.subcollection_slug,
            )
        except Subcollection.DoesNotExist:
            collection, created = Collection.objects.get_or_create(
                title=ciac.collection_task.collection_name,
                slug=ciac.collection_task.collection_slug,
                description=ciac.collection_task.collection_name,
                is_active=True,
            )

            subcollection = Subcollection.objects.create(
                title=ciac.collection_task.subcollection_name,
                collection=collection,
                slug=ciac.collection_task.subcollection_slug,
            )
        item_local_path = os.path.join(
            settings.IMPORTER["IMAGES_FOLDER"],
            subcollection.collection.slug,
            subcollection.slug,
            item_id,
        )

        save_collection_item_assets(subcollection, item_local_path, item_id)
        shutil.rmtree(
            os.path.join(
                settings.IMPORTER["IMAGES_FOLDER"],
                subcollection.collection.slug,
                subcollection.slug,
            )
        )
        return True

    return False
