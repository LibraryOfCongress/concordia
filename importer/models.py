from django.db import models

# FIXME: these classes should have names which more accurately represent what they do


class CampaignTaskDetails(models.Model):
    project = models.ForeignKey("concordia.Project", on_delete=models.CASCADE)
    campaign_item_count = models.IntegerField(null=True, blank=True, default=0)
    campaign_asset_count = models.IntegerField(null=True, blank=True, default=0)
    campaign_task_id = models.CharField(max_length=100, null=True, blank=True)


class CampaignItemAssetCount(models.Model):
    campaign_task = models.ForeignKey(CampaignTaskDetails, on_delete=models.CASCADE)
    campaign_item_identifier = models.CharField(max_length=80)
    campaign_item_asset_count = models.IntegerField(null=True, blank=True, default=0)
    item_task_id = models.CharField(max_length=100, null=True, blank=True)
