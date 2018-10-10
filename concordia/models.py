from logging import getLogger

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.postgres.fields import JSONField
from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django_prometheus_metrics.models import MetricsModelMixin


logger = getLogger(__name__)

metadata_default = dict

User._meta.get_field("email").__dict__["_unique"] = True


class UserProfile(MetricsModelMixin("userprofile"), models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)


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


class PublicationManager(models.Manager):
    def published(self):
        return self.get_queryset().filter(published=True)

    def unpublished(self):
        return self.get_queryset().filter(published=False)


class Campaign(MetricsModelMixin("campaign"), models.Model):
    objects = PublicationManager()

    published = models.BooleanField(default=False, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.CHOICES, default=Status.DEFAULT
    )

    title = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    thumbnail_image = models.ImageField(
        upload_to="campaign-thumbnails", blank=True, null=True
    )

    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)

    metadata = JSONField(default=metadata_default, blank=True, null=True)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        # FIXME: change this with https://github.com/LibraryOfCongress/concordia/issues/242
        return reverse("transcriptions:campaign", args=(self.slug,))


class Project(MetricsModelMixin("project"), models.Model):
    objects = PublicationManager()

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)
    title = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80)
    thumbnail_image = models.ImageField(
        upload_to="project-thumbnails", blank=True, null=True
    )

    category = models.CharField(max_length=12, blank=True)
    metadata = JSONField(default=metadata_default, blank=True, null=True)
    status = models.CharField(
        max_length=10, choices=Status.CHOICES, default=Status.DEFAULT
    )
    published = models.BooleanField(default=False, blank=True)

    class Meta:
        unique_together = (("slug", "campaign"),)
        ordering = ["title"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse(
            "transcriptions:project-detail",
            kwargs={"campaign_slug": self.campaign.slug, "slug": self.slug},
        )


class Item(MetricsModelMixin("item"), models.Model):
    objects = PublicationManager()

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, blank=True, null=True
    )

    published = models.BooleanField(default=False, blank=True)

    title = models.CharField(max_length=300)
    item_url = models.URLField(max_length=255)
    item_id = models.CharField(
        max_length=100, help_text="Unique item ID assigned by the upstream source"
    )
    description = models.TextField(blank=True)
    metadata = JSONField(
        default=metadata_default,
        blank=True,
        null=True,
        help_text="Raw metadata returned by the remote API",
    )
    thumbnail_url = models.URLField(max_length=255, blank=True, null=True)
    status = models.CharField(
        max_length=10, choices=Status.CHOICES, default=Status.DEFAULT
    )

    class Meta:
        unique_together = (("item_id", "project"),)

    def __str__(self):
        return f"{self.item_id}: {self.title}"

    def get_absolute_url(self):
        return reverse(
            "transcriptions:item",
            kwargs={
                "campaign_slug": self.project.campaign.slug,
                "project_slug": self.project.slug,
                "item_id": self.item_id,
            },
        )


class Asset(MetricsModelMixin("asset"), models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE)

    title = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100)

    description = models.TextField(blank=True)
    # TODO: do we really need this given that we import in lock-step sequence
    #       numbers with a fixed extension?
    media_url = models.TextField("Path component of the URL", max_length=255)
    media_type = models.CharField(
        max_length=4, choices=MediaType.CHOICES, db_index=True
    )
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
        unique_together = (("slug", "item"),)
        ordering = ["title", "sequence"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse(
            "transcriptions:asset-detail",
            kwargs={
                "campaign_slug": self.item.project.campaign.slug,
                "project_slug": self.item.project.slug,
                "item_id": self.item.item_id,
                "slug": self.slug,
            },
        )


class Tag(MetricsModelMixin("tag"), models.Model):
    TAG_VALIDATOR = RegexValidator(r"^[- _'\w]{1,50}$")
    value = models.CharField(max_length=50, validators=[TAG_VALIDATOR])

    def __str__(self):
        return self.value


class UserAssetTagCollection(
    MetricsModelMixin("user_asset_tag_collection"), models.Model
):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    tags = models.ManyToManyField(Tag, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "{} - {}".format(self.asset, self.user)


class Transcription(MetricsModelMixin("transcription"), models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    text = models.TextField(blank=True)
    status = models.CharField(
        max_length=10, choices=Status.CHOICES, default=Status.DEFAULT
    )

    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.asset)


class AssetTranscriptionReservation(models.Model):
    """
    Records a user's reservation to transcribe a particular asset
    """

    asset = models.OneToOneField(Asset, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    created_on = models.DateTimeField(editable=False, auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
