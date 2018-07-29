from django.contrib import admin

from .models import (Asset, Collection, Subcollection, Tag, Transcription,
                     UserAssetTagCollection)


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
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


@admin.register(Subcollection)
class SubcollectionAdmin(admin.ModelAdmin):
    # todo: replace metadata with truncated values
    # todo: add foreignKey link for collection
    list_display = (
        "id",
        "title",
        "slug",
        "category",
        "collection",
        "metadata",
        "status",
    )
    list_display_links = ("id", "title", "slug")


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
        "collection",
        "subcollection",
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
