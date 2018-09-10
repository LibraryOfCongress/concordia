from django.contrib import admin

from importer.models import CollectionItemAssetCount, CollectionTaskDetails


@admin.register(CollectionTaskDetails)
class CollectionTaskDetailsAdmin(admin.ModelAdmin):
    # todo: replace text with truncated value
    # todo: add foreignKey link for asset, parent, & user_id
    pass
    list_display = (
        "collection_name",
        "collection_slug",
        "collection_task_id",
        "collection_asset_count",
        "collection_item_count",
    )
    # list_display_links = ("collection_name")


@admin.register(CollectionItemAssetCount)
class CollectionItemAssetCountAdmin(admin.ModelAdmin):
    # todo: replace text with truncated value
    # todo: add foreignKey link for asset, parent, & user_id
    pass
    list_display = ("collection_item_identifier", "collection_item_asset_count")
