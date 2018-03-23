from logging import getLogger
from django.db.models import Count
from rest_framework import viewsets
from . import serializers
from . import models

logger = getLogger(__name__)


class CollectionListViewSet(viewsets.ModelViewSet):
    queryset = models.Collection.objects.order_by('title')
    serializer_class = serializers.CollectionListSerializer
    lookup_field = 'slug'
