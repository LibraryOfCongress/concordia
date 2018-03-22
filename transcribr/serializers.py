from rest_framework import serializers
from . import models


class CollectionSerializer(serializers.HyperlinkedModelSerializer):
    asset_count = serializers.IntegerField(
        source='asset_set.count', 
        read_only=True
    )
    class Meta:
        model = models.Collection
        fields = (
            'id',
            'title',
            'slug',
            'description',
            'start_date',
            'end_date',
            'status',
            'asset_count',
        )
