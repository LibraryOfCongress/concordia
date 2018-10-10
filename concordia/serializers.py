import boto3
from django.conf import settings
from django.contrib.auth.models import User
from rest_framework import serializers

from . import models


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
        fields = ("title", "item_id", "thumbnail_url", "assets", "project")


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
