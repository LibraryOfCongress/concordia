from rest_framework import serializers
from . import models


class CollectionListSerializer(serializers.HyperlinkedModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name='collection-detail',
        lookup_field='slug'
    )
    asset_count = serializers.IntegerField(
        source='asset_set.count', 
        read_only=True
    )
    class Meta:
        model = models.Collection
        fields = (
            'url',
            'slug',
            'title',
            'description',
            'start_date',
            'end_date',
            'status',
            'asset_count',
        )


class AssetSerializer(serializers.ModelSerializer):

    class Meta:
        model = models.Asset


class CollectionSerializer(serializers.ModelSerializer):

    class Meta:
        model = models.Collection
