from django.contrib import admin

from importer.models import CampaignItemAssetCount, CampaignTaskDetails


@admin.register(CampaignTaskDetails)
class CampaignTaskDetailsAdmin(admin.ModelAdmin):
    # todo: replace text with truncated value
    # todo: add foreignKey link for asset, parent, & user_id
    pass
    list_display = (
        "campaign_name",
        "campaign_slug",
        "campaign_task_id",
        "campaign_asset_count",
        "campaign_item_count",
    )
    # list_display_links = ("campaign_name")


@admin.register(CampaignItemAssetCount)
class CampaignItemAssetCountAdmin(admin.ModelAdmin):
    # todo: replace text with truncated value
    # todo: add foreignKey link for asset, parent, & user_id
    pass
    list_display = ("campaign_item_identifier", "campaign_item_asset_count")
