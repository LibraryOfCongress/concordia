from rest_framework import serializers
from django.contrib.auth.models import User

from . import models


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id",
                  "username",
                  "password",
                  "first_name",
                  "last_name",
                  "email",
                  "is_staff",
                  "is_active",
                  "date_joined"
                  )


class UserProfileSerializer(serializers.ModelSerializer):

    class Meta:
        model = models.UserProfile
        fields = ("id",
                  "user",
                  "myfile",
                  )


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
            "is_publish",
        )


class AssetSetForCollectionSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = models.Asset
        fields = (
            "id",
            "title",
            "slug",
            "description",
            "media_url",
            "media_type",
            "sequence",
            "metadata",
            "status",
        )


class SubcollectionSerializer(serializers.ModelSerializer):

    class Meta:
        model = models.Subcollection
        fields = (
            "id",
            "title",
            "slug",
            "metadata",
            "status",
            "is_publish",
        )


class CollectionDetailSerializer(serializers.HyperlinkedModelSerializer):
    assets = AssetSetForCollectionSerializer(source="asset_set", many=True)
    subcollections = SubcollectionSerializer(source="subcollection_set", many=True)

    class Meta:
        model = models.Collection
        fields = (
            "id",
            "slug",
            "title",
            "description",
            "s3_storage",
            "start_date",
            "end_date",
            "status",
            "subcollections",
            "assets",
        )


class AssetSerializer(serializers.HyperlinkedModelSerializer):
    collection = CollectionDetailSerializer()
    subcollection = SubcollectionSerializer()

    class Meta:
        model = models.Asset
        fields = (
            "id",
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
            page_url=validated_data["page_url"], user=validated_data["user"]
        )
        page_in_use.save()

    def delete_old(self):
        from datetime import datetime, timedelta

        time_threshold = datetime.now() - timedelta(minutes=5)
        old_page_entries = models.PageInUse.objects.filter(
            updated_on__lt=time_threshold
        )
        for old_page in old_page_entries:
            old_page.delete()

    def create(self, validated_data):
        page_in_use = models.PageInUse(
            page_url=validated_data["page_url"], user=validated_data["user"]
        )
        page_in_use.save()

        # On every insertion, delete any entries not updated in the last 5 minutes
        self.delete_old()

        return page_in_use

    def update(self, instance, validated_data):
        instance.save()
        self.delete_old()
        return instance

    class Meta:
        model = models.PageInUse
        fields = ("page_url", "user", "updated_on")

class TranscriptionSerializer(serializers.HyperlinkedModelSerializer):
    asset = AssetSerializer()

    class Meta:
        model = models.Transcription
        fields = ("id", "asset", "user_id", "text", "status", "updated_on")


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Tag
        fields = ("name", "value")


class UserAssetTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.UserAssetTagCollection
        fields = ("asset", "user_id", "tags")
