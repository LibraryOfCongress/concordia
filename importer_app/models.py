from django.db import models


class CollectionTaskDetails(models.Model):
    collection_name = models.CharField(max_length=50)
    collection_slug = models.SlugField(max_length=50, unique=True)
    collection_page_count = models.IntegerField(null=True, blank=True, default=0)
    collection_item_count = models.IntegerField(null=True, blank=True, default=0)
    collection_asset_count = models.IntegerField(null=True, blank=True, default=0)
    collection_task_id = models.CharField(max_length=100,null=True, blank=True)


class CollectionItemAssetCount(models.Model):
    collection_slug = models.SlugField(max_length=50)
    collection_item_identifier = models.CharField(max_length=50)
    collection_item_asset_count = models.IntegerField(null=True, blank=True, default=0)
