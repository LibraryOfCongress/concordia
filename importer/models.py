from django.db import models


class CollectionTaskDetails(models.Model):
    collection_name = models.CharField(max_length=50)
    collection_slug = models.SlugField(max_length=50)
    subcollection_name = models.CharField(max_length=250)
    subcollection_slug = models.SlugField(max_length=250)
    # collection_page_count = models.IntegerField(null=True, blank=True, default=0)
    collection_item_count = models.IntegerField(null=True, blank=True, default=0)
    collection_asset_count = models.IntegerField(null=True, blank=True, default=0)
    collection_task_id = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        unique_together = ("collection_slug", "subcollection_slug")


class CollectionItemAssetCount(models.Model):
    # collection_slug = models.SlugField(max_length=50)
    collection_task = models.ForeignKey(CollectionTaskDetails, on_delete=models.CASCADE)
    collection_item_identifier = models.CharField(max_length=50)
    collection_item_asset_count = models.IntegerField(null=True, blank=True, default=0)
    item_task_id = models.CharField(max_length=100, null=True, blank=True)
