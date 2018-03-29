from logging import getLogger
from django.db.models import Count

from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse

from . import serializers
from . import models

logger = getLogger(__name__)


@api_view(['GET'])
def api_root(request, format=None):
    return Response({
        'collections': reverse('collection-list', request=request, format=format),
        #'collection': reverse('collection-detail', request=request, format=format),
    })


class CollectionList(viewsets.ModelViewSet):
    queryset = models.Collection.objects.order_by('title')
    serializer_class = serializers.CollectionListSerializer



class CollectionDetail(viewsets.ModelViewSet):
    queryset = models.Collection.objects.order_by('title')
    serializer_class = serializers.CollectionDetailSerializer
