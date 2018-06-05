from rest_framework import serializers

from . import models


class CollectionListSerializer(serializers.ModelSerializer):
    asset_count = serializers.IntegerField(source="asset_set.count", read_only=True)

    class Meta:
        model = models.Collection
        fields = (
            "id",
            "slug",
            "title",
            "description",
            "start_date",
            "end_date",
            "status",
            "asset_count",
        )


class CollectionDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Collection
        fields = (
            "id",
            "slug",
            "title",
            "description",
            "start_date",
            "end_date",
            "status",
        )


class AssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Asset
