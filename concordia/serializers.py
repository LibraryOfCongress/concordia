import boto3
from rest_framework import serializers
from django.contrib.auth.models import User
from django.conf import settings

from . import models

S3_BUCKET_NAME = settings.AWS_S3.get("S3_COLLECTION_BUCKET", "")
S3_CLIENT = boto3.client('s3', settings.AWS_S3.get("REGION", ""))


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
            "is_publish",
        )


class AssetSetSerializer(serializers.HyperlinkedModelSerializer):

    media_url = serializers.SerializerMethodField()

    def get_media_url(self, obj):
        if S3_BUCKET_NAME and obj:
            url = '{}/{}/{}'.format(S3_CLIENT.meta.endpoint_url, S3_BUCKET_NAME, obj.media_url)
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
        fields = (
            "id",
            "title",
            "slug",
            "metadata",
            "status",
            "is_publish",
        )


class CampaignDetailSerializer(serializers.HyperlinkedModelSerializer):
    assets = AssetSetSerializer(source="asset_set", many=True)
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
            "assets",
        )


class ItemSerializer(serializers.ModelSerializer):
    assets = AssetSetSerializer(source="asset_set", many=True)
    campaign = CampaignDetailSerializer()
    project = ProjectSerializer()

    class Meta:
        model = models.Item
        fields = (
            "title",
            "slug",
            "thumbnail_url",
            "assets",
            "project",
            "campaign",
        )


class AssetSerializer(serializers.HyperlinkedModelSerializer):
    campaign = CampaignDetailSerializer()
    project = ProjectSerializer()
    media_url = serializers.SerializerMethodField()

    def get_media_url(self, obj):
        if S3_BUCKET_NAME and obj:
            url = '{}/{}/{}'.format(S3_CLIENT.meta.endpoint_url, S3_BUCKET_NAME, obj.media_url)
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
            "campaign",
            "project",
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
