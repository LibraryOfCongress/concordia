from django.db.models import Count
from rest_framework import viewsets
from . import serializers
from . import models


class CollectionViewSet(viewsets.ModelViewSet):
    queryset = models.Collection.objects.all()
    serializer_class = serializers.CollectionSerializer

