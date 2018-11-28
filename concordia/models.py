from logging import getLogger

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.postgres.fields import JSONField
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse
from django_prometheus_metrics.models import MetricsModelMixin

logger = getLogger(__name__)

metadata_default = dict

User._meta.get_field("email").__dict__["_unique"] = True


class UserProfile(MetricsModelMixin("userprofile"), models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)


class TranscriptionStatus(object):
    """
    Status values used for rollup summaries of an asset's transcription status
    to avoid needing to do nested queries in views
    """

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    COMPLETED = "completed"

    CHOICES = (
        (NOT_STARTED, "Not Started"),
        (IN_PROGRESS, "In Progress"),
        (SUBMITTED, "Submitted for Review"),
        (COMPLETED, "Completed"),
    )
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

    ordering = models.IntegerField(
        default=0, help_text="Sort order override: higher values will be listed first"
    )
    display_on_homepage = models.BooleanField(default=True)

    title = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    thumbnail_image = models.ImageField(
        upload_to="campaign-thumbnails", blank=True, null=True
    )
    short_description = models.TextField(blank=True)

    metadata = JSONField(default=metadata_default, blank=True, null=True)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("transcriptions:campaign-detail", args=(self.slug,))


class Resource(MetricsModelMixin("resource"), models.Model):
    sequence = models.PositiveIntegerField(default=1)
    title = models.CharField(blank=False, max_length=255)
    resource_url = models.URLField()

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)

    class Meta:
        unique_together = (("campaign", "sequence"),)
        ordering = ["campaign", "sequence"]

    def __str__(self):
        return self.title


class Project(MetricsModelMixin("project"), models.Model):
    objects = PublicationManager()

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)

    published = models.BooleanField(default=False, blank=True)

    title = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80)
    thumbnail_image = models.ImageField(
        upload_to="project-thumbnails", blank=True, null=True
    )

    description = models.TextField(blank=True)
    category = models.CharField(max_length=12, blank=True)
    metadata = JSONField(default=metadata_default, blank=True, null=True)

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

    project = models.ForeignKey(Project, on_delete=models.CASCADE)

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

    class Meta:
        unique_together = (("item_id", "project"),)

    def __str__(self):
        return f"{self.item_id}: {self.title}"

    def get_absolute_url(self):
        return reverse(
            "transcriptions:item-detail",
            kwargs={
                "campaign_slug": self.project.campaign.slug,
                "project_slug": self.project.slug,
                "item_id": self.item_id,
            },
        )


class Asset(MetricsModelMixin("asset"), models.Model):
    objects = PublicationManager()

    item = models.ForeignKey(Item, on_delete=models.CASCADE)

    published = models.BooleanField(default=False, blank=True)

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
    resource_url = models.URLField(max_length=255, blank=True, null=True)
    # The URL used to download this image from loc.gov
    download_url = models.CharField(max_length=255, blank=True, null=True)

    metadata = JSONField(default=metadata_default, blank=True, null=True)

    # This is computed from the Transcription records and should never
    # be directly modified except by the Transcription signal handler:
    transcription_status = models.CharField(
        editable=False,
        max_length=20,
        default=TranscriptionStatus.NOT_STARTED,
        choices=TranscriptionStatus.CHOICES,
    )

    class Meta:
        unique_together = (("slug", "item"),)

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

    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    supersedes = models.ForeignKey(
        "self",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        help_text="A previous transcription record which is replaced by this one",
        related_name="superseded_by",
    )

    submitted = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Timestamp when the creator submitted this for review",
    )

    # Review tracking:
    accepted = models.DateTimeField(blank=True, null=True)
    rejected = models.DateTimeField(blank=True, null=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="transcription_reviewers",
    )

    text = models.TextField(blank=True)

    def __str__(self):
        return f"Transcription #{self.pk}"

    def clean(self):
        if self.user and self.reviewed_by and self.user == self.reviewed_by:
            raise ValidationError("Transcriptions cannot be self-reviewed")
        if self.accepted and self.rejected:
            raise ValidationError("Transcriptions cannot be both accepted and rejected")
        return super().clean()

    @property
    def status(self):
        if self.accepted:
            return TranscriptionStatus.CHOICE_MAP[TranscriptionStatus.COMPLETED]
        elif self.submitted and not self.rejected:
            return TranscriptionStatus.CHOICE_MAP[TranscriptionStatus.SUBMITTED]
        else:
            return TranscriptionStatus.CHOICE_MAP[TranscriptionStatus.IN_PROGRESS]


class AssetTranscriptionReservation(models.Model):
    """
    Records a user's reservation to transcribe a particular asset
    """

    asset = models.OneToOneField(Asset, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    created_on = models.DateTimeField(editable=False, auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
