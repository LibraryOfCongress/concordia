from django.db import models


class CampaignTaskDetails(models.Model):
    campaign_name = models.CharField(max_length=50)
    campaign_slug = models.SlugField(max_length=50)
    project_name = models.CharField(max_length=250)
    project_slug = models.SlugField(max_length=250)
    campaign_item_count = models.IntegerField(null=True, blank=True, default=0)
    campaign_asset_count = models.IntegerField(null=True, blank=True, default=0)
    campaign_task_id = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        unique_together = ("campaign_slug", "project_slug")


class CampaignItemAssetCount(models.Model):
    campaign_task = models.ForeignKey(CampaignTaskDetails, on_delete=models.CASCADE)
    campaign_item_identifier = models.CharField(max_length=50)
    campaign_item_asset_count = models.IntegerField(null=True, blank=True, default=0)
    item_task_id = models.CharField(max_length=100, null=True, blank=True)
