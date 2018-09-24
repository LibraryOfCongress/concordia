from django.contrib import admin

from .models import (
    Asset,
    Campaign,
    Item,
    Project,
    Tag,
    Transcription,
    UserAssetTagCollection,
)


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    # todo: replace description & metadata with truncated values
    list_display = (
        "id",
        "title",
        "slug",
        "description",
        "start_date",
        "end_date",
        "metadata",
        "is_active",
        "s3_storage",
        "status",
    )
    list_display_links = ("id", "title", "slug")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    # todo: replace metadata with truncated values
    # todo: add foreignKey link for campaign
    list_display = ("id", "title", "slug", "category", "campaign", "metadata", "status")
    list_display_links = ("id", "title", "slug")


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "slug",
        "item_id",
        "campaign",
        "project",
        "status",
        "is_publish",
    )
    list_display_links = ("title", "slug", "item_id")


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    # todo: add truncated values for description & metadata
    list_display = (
        "id",
        "title",
        "slug",
        # 'description',
        "media_url",
        "media_type",
        "campaign",
        "project",
        "sequence",
        # 'metadata',
        "status",
    )
    list_display_links = ("id", "title", "slug")


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "value")
    list_display_links = ("id", "name", "value")


@admin.register(UserAssetTagCollection)
class UserAssetTagCollectionAdmin(admin.ModelAdmin):
    # todo: add foreignKey link for asset & user_id
    pass
    list_display = ("id", "asset", "user_id", "created_on", "updated_on")
    list_display_links = ("id", "asset")


@admin.register(Transcription)
class TranscriptionAdmin(admin.ModelAdmin):
    # todo: replace text with truncated value
    # todo: add foreignKey link for asset, parent, & user_id
    pass
    list_display = (
        "id",
        "asset",
        "parent",
        "user_id",
        "text",
        "status",
        "created_on",
        "updated_on",
    )
    list_display_links = ("id", "asset")
