import boto3
from django.conf import settings
from django.contrib.auth.models import User
from rest_framework import serializers

from . import models

S3_BUCKET_NAME = settings.AWS_S3.get("S3_COLLECTION_BUCKET", "")
S3_CLIENT = boto3.client("s3", settings.AWS_S3.get("REGION", ""))


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username")


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.UserProfile
        fields = ("id", "user", "myfile")


class CampaignListSerializer(serializers.ModelSerializer):
    asset_count = serializers.IntegerField(source="asset_set.count", read_only=True)

    class Meta:
        model = models.Campaign
        fields = (
            "id",
            "slug",
            "title",
            "description",
            "start_date",
            "end_date",
            "status",
            "asset_count",
            "published",
        )


class AssetSetSerializer(serializers.HyperlinkedModelSerializer):

    media_url = serializers.SerializerMethodField()

    def get_media_url(self, obj):
        if S3_BUCKET_NAME and obj:
            url = "{}/{}/{}".format(
                S3_CLIENT.meta.endpoint_url, S3_BUCKET_NAME, obj.media_url
            )
            return url
        else:
            return obj.media_url

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


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Project
        fields = ("id", "title", "slug", "metadata", "status", "published")


class CampaignDetailSerializer(serializers.HyperlinkedModelSerializer):
    projects = ProjectSerializer(source="project_set", many=True)

    class Meta:
        model = models.Campaign
        fields = (
            "id",
            "slug",
            "title",
            "description",
            "s3_storage",
            "start_date",
            "end_date",
            "status",
            "projects",
        )


class ItemSerializer(serializers.ModelSerializer):
    assets = AssetSetSerializer(source="asset_set", many=True)
    project = ProjectSerializer()

    class Meta:
        model = models.Item
        fields = ("title", "slug", "thumbnail_url", "assets", "project")


class AssetSerializer(serializers.HyperlinkedModelSerializer):
    item = ItemSerializer()
    media_url = serializers.SerializerMethodField()

    def get_media_url(self, obj):
        if S3_BUCKET_NAME and obj:
            url = "{}/{}/{}".format(
                S3_CLIENT.meta.endpoint_url, S3_BUCKET_NAME, obj.media_url
            )
            return url
        else:
            return obj.media_url

    class Meta:
        model = models.Asset
        fields = (
            "id",
            "title",
            "slug",
            "description",
            "media_url",
            "media_type",
            "item",
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

        # On every insertion, delete any entries not updated in the last 5 minutes
        self.delete_old()

        return page_in_use

    def delete_old(self):
        from datetime import datetime, timedelta

        # FIXME: use a setting for the threshold
        time_threshold = datetime.now() - timedelta(minutes=5)
        # FIXME: is there any reason such as a signal which means we can't just call delete on this queryset?
        old_page_entries = models.PageInUse.objects.filter(
            updated_on__lt=time_threshold
        )
        for old_page in old_page_entries:
            old_page.delete()

    def update(self, instance, validated_data):
        instance.save()
        self.delete_old()
        return instance

    class Meta:
        model = models.PageInUse
        fields = ("page_url", "user", "updated_on")


class TranscriptionSerializer(serializers.HyperlinkedModelSerializer):
    asset = AssetSerializer()
    user = UserSerializer()

    class Meta:
        model = models.Transcription
        fields = ("id", "asset", "user", "text", "status", "updated_on")


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Tag
        fields = ("value",)


class UserAssetTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.UserAssetTagCollection
        fields = ("asset", "user", "tags")
