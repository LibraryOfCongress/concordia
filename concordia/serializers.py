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
        fields = (
            "title",
            "slug",
            "description",
            "media_url",
            "media_type",
            "collection",
            "subcollection",
            "sequence",
            "metadata",
            "status",
        )


class PageInUseSerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        page_in_use = models.PageInUse(
            page_url=validated_data["page_url"],
            user=validated_data["user"]
        )
        page_in_use.save()

        # On every insertion, delete any entries not updated in the last 5 minutes
        from datetime import datetime, timedelta

        time_threshold = datetime.now() - timedelta(minutes=5)
        old_page_entries = models.PageInUse.objects.filter(updated_on__lt=time_threshold)
        for old_page in old_page_entries:
            old_page.delete()

        return page_in_use

    def update(self, instance, validated_data):
        instance.save()
        return instance

    class Meta:
        model = models.PageInUse
        fields = (
            "page_url",
            "user"
        )


class TranscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Transcription
        fields = (
            "asset",
            "user_id",
            "text",
            "status"
        )


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Tag
        fields = ("name", "value")


class UserAssetTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.UserAssetTagCollection
        fields = (
            "asset", "user_id", "tags"
            )
