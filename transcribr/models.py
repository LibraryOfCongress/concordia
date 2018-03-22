from django.db import models
from django.urls import reverse
from django.conf import settings

class Status:
    PCT_0    = '0'
    PCT_25   = '25'
    PCT_50   = '50'
    PCT_75   = '75'
    PCT_100  = '100'
    COMPLETE = 'DONE'

    DEFAULT = PCT_0
    CHOICES = (
        (PCT_0,    '0%'),
        (PCT_25,   '25%'),
        (PCT_50,   '50%'),
        (PCT_75,   '75%'),
        (PCT_100,  '100%'),
        (COMPLETE, 'Complete'),
    )


class MediaType:
    IMAGE = 'IMG'
    AUDIO = 'AUD'
    VIDEO = 'VID'

    CHOICES = (
        (IMAGE, 'Image'),
        (AUDIO, 'Audio'),
        (VIDEO, 'Video'),
    )


class Collection(models.Model):
    title = models.CharField(max_length=50)
    slug = models.SlugField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=4,
        choices=Status.CHOICES,
        default=Status.DEFAULT
    )

    def __str__(self):
        return self.title


class Subcollection(models.Model):
    title = models.CharField(max_length=50)
    slug = models.SlugField(max_length=50)
    category = models.CharField(max_length=12, blank=True)
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=4,
        choices=Status.CHOICES,
        default=Status.DEFAULT
    )

    class Meta:
        unique_together = (("slug", "collection"),)


class Asset(models.Model):
    title = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100)
    description = models.TextField(blank=True)
    media_url = models.URLField(max_length=255)
    media_type = models.CharField(
        max_length=4,
        choices=MediaType.CHOICES,
        db_index=True
    )
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE)
    subcollection = models.ForeignKey(Subcollection, on_delete=models.CASCADE, blank=True, null=True)
    sequence = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=4,
        choices=Status.CHOICES,
        default=Status.DEFAULT
    )

    class Meta:
        unique_together = (("slug", "collection"),)

    def __str__(self):
        return self.title


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    value = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.value


class UserAssetTagCollection(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    user_id = models.PositiveIntegerField(db_index=True)
    tags = models.ManyToManyField(Tag, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return '{} - {}'.format(self.asset, self.user_id)


class Trascription(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    parent = models.ForeignKey('self', blank=True, null=True, on_delete=models.SET_NULL)
    user_id = models.PositiveIntegerField(db_index=True)
    text = models.TextField(blank=True)
    status = models.CharField(
        max_length=4,
        choices=Status.CHOICES,
        default=Status.DEFAULT
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)


