import os
import shutil

from logging import getLogger
from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from importer.importer.tasks import download_async_collection, check_completeness


class UserProfile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    myfile = models.FileField(upload_to='profile_pics/')

if settings.USE_POSTGRES:
    from django.contrib.postgres.fields import JSONField
    metadata_default = dict
else:
    JSONField = models.TextField()

    def metadata_default():
        return ''

logger = getLogger(__name__)


class Status:
    PCT_0 = '0'
    PCT_25 = '25'
    PCT_50 = '50'
    PCT_75 = '75'
    PCT_100 = '100'
    COMPLETE = 'DONE'

    DEFAULT = PCT_0
    CHOICES = (
        (PCT_0, '0%'),
        (PCT_25, '25%'),
        (PCT_50, '50%'),
        (PCT_75, '75%'),
        (PCT_100, '100%'),
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
    metadata = JSONField(default=metadata_default)
    is_active = models.BooleanField(default=False)
    status = models.CharField(
        max_length=4,
        choices=Status.CHOICES,
        default=Status.DEFAULT
    )

    def __str__(self):
        return self.title

    def copy_images_to_collection(self, url, collection_path):
        result2 = None
        try:
            result = download_async_collection.delay(url)
            result.ready()
            result.get()
            result2 = check_completeness.delay()
            result2.ready()
            result2.get()
        except Exception as e:
            print(e)
            pass

        if result2 and not result2.state == 'PENDING':
            if os.path.isdir(collection_path):
                shutil.rmtree(collection_path)
            shutil.copytree('/concordia_images', collection_path):
            shutil.rmtree('/concordia_images/')

    def create_assets_from_filesystem(self, collection_path):
        for root, dirs, files in os.walk(collection_path):
            for filename in files:
                file_path = os.path.join(root, filename)
                title = file_path.replace(collection_path + '/', '').split('/')[0]
                media_url = file_path.replace(settings.MEDIA_ROOT, '')
                sequence = int(os.path.splitext(filename)[0])
                Asset.objects.create(title=title,
                                     slug="{0}{1}".format(title, sequence),
                                     description="{0} description".format(title),
                                     media_url=media_url,
                                     media_type='IMG',
                                     sequence=sequence,
                                     collection=self)


class Subcollection(models.Model):
    title = models.CharField(max_length=50)
    slug = models.SlugField(max_length=50)
    category = models.CharField(max_length=12, blank=True)
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE)
    metadata = JSONField(default=metadata_default)
    status = models.CharField(
        max_length=4,
        choices=Status.CHOICES,
        default=Status.DEFAULT
    )

    class Meta:
        unique_together = (("slug", "collection"),)
        ordering = ['title']


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
    metadata = JSONField(default=metadata_default)
    status = models.CharField(
        max_length=4,
        choices=Status.CHOICES,
        default=Status.DEFAULT
    )

    class Meta:
        unique_together = (("slug", "collection"),)
        ordering = ['title', 'sequence']

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


class Transcription(models.Model):
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

    def __str__(self):
        return str(self.asset)
