from celery.result import AsyncResult

from rest_framework import generics
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view

from importer_app.serializer import CreateCollection
from importer_app.tasks import download_write_collection_item_assets


class CreateCollectionView(generics.CreateAPIView):
    serializer_class = CreateCollection


    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        name = serializer.data.get('collection_name')
        url = serializer.data.get('collection_url')
        bb = download_write_collection_item_assets.delay(name, url)
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


