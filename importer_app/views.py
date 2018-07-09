import os
from logging import getLogger
from celery.result import AsyncResult

from django.conf import settings
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render

from rest_framework import generics
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view

from importer_app.serializer import CreateCollection
from importer_app.tasks import download_write_collection_item_assets
from importer_app.models import CollectionTaskDetails, CollectionItemAssetCount

from concordia.models import Collection, Asset

logger = getLogger(__name__)


class CreateCollectionView(generics.CreateAPIView):
    serializer_class = CreateCollection


    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        name = serializer.data.get('name')
        url = serializer.data.get('url')
        collection_details = {'collection_name': name, "collection_slug": name}
        bb = download_write_collection_item_assets.delay(name, url)
        collection_details['collection_task_id'] = bb.task_id
        ctd = CollectionTaskDetails.objects.create(**collection_details)
        ctd.save()
        data = serializer.data
        data['task_id'] = bb.task_id

        headers = self.get_success_headers(data)

        return Response(data, status=status.HTTP_201_CREATED,
                        headers=headers)


@api_view(['GET'])
def get_task_status(request, task_id):
    if request.method == 'GET':

        celery_task_result = AsyncResult(task_id)
        task_state = celery_task_result.state
        return Response(task_state)


def check_collection_completeness(ctd):
    collection_local_path = os.path.join(settings.IMPORTER['IMAGES_FOLDER'], ctd.collection_name)
    collection_items = os.listdir(collection_local_path)
    collection_downloaded_item_count = len(collection_items)
    collection_downloaded_asset_count = sum([len(files) for path, dirs, files in os.walk(collection_local_path)])
    if (collection_downloaded_asset_count == ctd.collection_asset_count) and (collection_downloaded_item_count == ctd.collection_item_count):
        for ci in collection_items:
            item_local_path = os.path.join(collection_local_path, ci)
            item_downloaded_asset_count = sum([len(files) for path, dirs, files in os.walk(item_local_path)])
            ciac = CollectionItemAssetCount.objects.get(collection_slug=ctd.collection_slug, collection_item_identifier=ci)
            if ciac.collection_item_asset_count != item_downloaded_asset_count:
                return False
        return True
    else:
        return False


def save_collection_item_assets(collection):
    collection_local_path = os.path.join(settings.IMPORTER['IMAGES_FOLDER'], collection.slug)
    for root, dirs, files in os.walk(collection_local_path):
        for filename in files:
            file_path = os.path.join(root, filename)
            title = file_path.replace(collection_local_path + "/", "").split("/")[0]
            media_url = file_path.replace(settings.IMPORTER['IMAGES_FOLDER'], "")
            sequence = int(os.path.splitext(filename)[0])
            Asset.objects.create(
                title=title,
                slug="{0}{1}".format(title, sequence),
                description="{0} description".format(title),
                media_url=media_url,
                media_type="IMG",
                sequence=sequence,
                collection=collection,
            )
            import shutil

            try:
                item_path = "/".join(os.path.join(settings.MEDIA_ROOT, media_url).split("/")[:-1])
                os.makedirs(item_path)
            except Exception as e:
                logger.error("Error/warning while creating dir path: %s" % e)

            shutil.move(file_path, os.path.join(settings.MEDIA_ROOT, media_url))


@api_view(['GET'])
def check_and_save_collection_assets(request, task_id):
    if request.method == 'GET':
        try:
            ctd = CollectionTaskDetails.objects.get(collection_task_id=task_id)

            if check_collection_completeness(ctd):
                collection = Collection.objects.create(title=ctd.collection_name, slug=ctd.collection_slug, description=ctd.collection_name, is_active= True)
                collection.save()

                save_collection_item_assets(collection)

                return redirect(
                    reverse(
                        "transcriptions:collection",
                        args=[ctd.collection_slug],
                        current_app=request.resolver_match.namespace,
                    )
                )
            else:
                return Response({'message': 'Creating a collection: %s is failed since assets are not completely downloaded'%ctd.collection_name}, status=status.HTTP_404_NOT_FOUND)
        except CollectionTaskDetails.DoesNotExist as e:
            logger.error("Requested Collection Details are not found with task id : %s" % task_id)
            return Response({'message': "Requested Collection Does not exists"})
