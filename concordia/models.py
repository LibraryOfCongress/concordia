from logging import getLogger

from django.contrib.auth.models import User
from django.contrib.postgres.fields import JSONField
from django.db import models
from django.utils import timezone
from django_prometheus_metrics.models import MetricsModelMixin

metadata_default = dict

User._meta.get_field("email").__dict__["_unique"] = True


class UserProfile(MetricsModelMixin("userprofile"), models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    myfile = models.FileField(upload_to="profile_pics/")


logger = getLogger(__name__)


class Status:
    # FIXME: determine whether this is actually universally applicable to all of
    # our models or should be split into subsets
    EDIT = "Edit"
    SUBMITTED = "Submitted"
    COMPLETED = "Completed"
    INACTIVE = "Inactive"
    ACTIVE = "Active"

    DEFAULT = EDIT
    CHOICES = (
        (EDIT, "Open for Edit"),
        (SUBMITTED, "Submitted for Review"),
        (COMPLETED, "Transcription Completed"),
        (INACTIVE, "Inactive"),
        (ACTIVE, "Active"),
    )

    #: Convenience lookup dictionary for CHOICES:
    CHOICE_MAP = dict(CHOICES)


class MediaType:
    IMAGE = "IMG"
    AUDIO = "AUD"
    VIDEO = "VID"

    CHOICES = ((IMAGE, "Image"), (AUDIO, "Audio"), (VIDEO, "Video"))


class Campaign(MetricsModelMixin("campaign"), models.Model):
    title = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    metadata = JSONField(default=metadata_default, blank=True, null=True)
    is_active = models.BooleanField(default=False)
    s3_storage = models.BooleanField(default=False)
    status = models.CharField(
        max_length=10, choices=Status.CHOICES, default=Status.DEFAULT
    )
    is_publish = models.BooleanField(default=False, blank=True)

    def __str__(self):
        return self.title


class Project(models.Model):
    title = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80)
    category = models.CharField(max_length=12, blank=True)
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)
    metadata = JSONField(default=metadata_default, blank=True, null=True)
    status = models.CharField(
        max_length=10, choices=Status.CHOICES, default=Status.DEFAULT
    )
    is_publish = models.BooleanField(default=False, blank=True)

    class Meta:
        unique_together = (("slug", "campaign"),)
        ordering = ["title"]

    def __str__(self):
        return self.title


class Item(models.Model):
    title = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100)
    description = models.TextField(blank=True)
    item_url = models.URLField(max_length=255)
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, blank=True, null=True
    )
    item_id = models.CharField(max_length=100, blank=True)
    metadata = JSONField(default=metadata_default, blank=True, null=True)
    thumbnail_url = models.URLField(max_length=255)
    status = models.CharField(
        max_length=10, choices=Status.CHOICES, default=Status.DEFAULT
    )
    is_publish = models.BooleanField(default=False, blank=True)

    class Meta:
        unique_together = (("item_id", "campaign"),)
        ordering = ["item_id"]

    def __str__(self):
        return self.item_id


class Asset(models.Model):
    title = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100)
    description = models.TextField(blank=True)
    media_url = models.TextField(max_length=255)
    media_type = models.CharField(
        max_length=4, choices=MediaType.CHOICES, db_index=True
    )
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, blank=True, null=True
    )
    item = models.ForeignKey(Item, blank=True, null=True, on_delete=models.CASCADE)
    sequence = models.PositiveIntegerField(default=1)

    # The original ID of the image resource on loc.gov
    resource_id = models.CharField(max_length=100, blank=True, null=True)
    # The URL used to download this image from loc.gov
    download_url = models.CharField(max_length=255, blank=True, null=True)

    metadata = JSONField(default=metadata_default, blank=True, null=True)
    status = models.CharField(
        max_length=10, choices=Status.CHOICES, default=Status.DEFAULT
    )

    class Meta:
        unique_together = (("slug", "campaign"),)
        ordering = ["title", "sequence"]

    def __str__(self):
        return self.title


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    value = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.value


class UserAssetTagCollection(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)

    # FIXME: why is this not a foreignkey on User?
    user_id = models.PositiveIntegerField(db_index=True)

    tags = models.ManyToManyField(Tag, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "{} - {}".format(self.asset, self.user_id)


class Transcription(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    parent = models.ForeignKey("self", blank=True, null=True, on_delete=models.SET_NULL)
    user_id = models.PositiveIntegerField(db_index=True)
    text = models.TextField(blank=True)
    status = models.CharField(
        max_length=10, choices=Status.CHOICES, default=Status.DEFAULT
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.asset)


class PageInUse(models.Model):
    page_url = models.CharField(max_length=256)
    user = models.ForeignKey(User, models.DO_NOTHING)
    created_on = models.DateTimeField(editable=False)
    updated_on = models.DateTimeField()

    def save(self, force_insert=False, *args, **kwargs):
        updated = False
        if self.pk and not force_insert:
            updated = self.custom_update()
        if not updated:
            self.custom_insert()
        return super(PageInUse, self).save(*args, **kwargs)

    def custom_update(self):
        self.updated_on = timezone.now()
        return True

    def custom_insert(self):
        self.created_on = timezone.now()
        if not self.updated_on:
            self.updated_on = timezone.now()
