from logging import getLogger

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.postgres.fields import JSONField
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Count
from django.urls import reverse
from django_prometheus_metrics.models import MetricsModelMixin

logger = getLogger(__name__)

metadata_default = dict

User._meta.get_field("email").__dict__["_unique"] = True


class UserProfile(MetricsModelMixin("userprofile"), models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)


class OverlayPosition(object):
    """
    Used in carousel slide content management
    """

    LEFT = "left"
    RIGHT = "right"

    CHOICES = ((LEFT, "Left"), (RIGHT, "Right"))
    CHOICE_MAP = dict(CHOICES)


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
        (SUBMITTED, "Needs Review"),
        (COMPLETED, "Completed"),
    )
    CHOICE_MAP = dict(CHOICES)


class MediaType:
    IMAGE = "IMG"
    AUDIO = "AUD"
    VIDEO = "VID"

    CHOICES = ((IMAGE, "Image"), (AUDIO, "Audio"), (VIDEO, "Video"))


class PublicationQuerySet(models.QuerySet):
    def published(self):
        return self.filter(published=True)

    def unpublished(self):
        return self.filter(published=False)


class UnlistedPublicationQuerySet(PublicationQuerySet):
    def listed(self):
        return self.filter(unlisted=False)

    def unlisted(self):
        return self.filter(unlisted=True)


class Campaign(MetricsModelMixin("campaign"), models.Model):
    objects = UnlistedPublicationQuerySet.as_manager()

    published = models.BooleanField(default=False, blank=True, db_index=True)
    unlisted = models.BooleanField(default=False, blank=True, db_index=True)

    ordering = models.IntegerField(
        default=0, help_text="Sort order override: lower values will be listed first"
    )
    display_on_homepage = models.BooleanField(default=True)

    title = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, unique=True, allow_unicode=True)
    description = models.TextField(blank=True)
    thumbnail_image = models.ImageField(
        upload_to="campaign-thumbnails", blank=True, null=True
    )
    short_description = models.TextField(blank=True)

    metadata = JSONField(default=metadata_default, blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["published", "unlisted"]),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("transcriptions:campaign-detail", args=(self.slug,))


class Topic(models.Model):
    objects = UnlistedPublicationQuerySet.as_manager()

    published = models.BooleanField(default=False, blank=True, db_index=True)
    unlisted = models.BooleanField(default=False, blank=True, db_index=True)

    ordering = models.IntegerField(
        default=0, help_text="Sort order override: lower values will be listed first"
    )
    title = models.CharField(blank=False, max_length=255)
    slug = models.SlugField(blank=False, allow_unicode=True, max_length=80)
    description = models.TextField(blank=True)
    thumbnail_image = models.ImageField(
        upload_to="topic-thumbnails", blank=True, null=True
    )
    short_description = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["published", "unlisted"]),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("topic-detail", kwargs={"slug": self.slug})


class Resource(MetricsModelMixin("resource"), models.Model):
    sequence = models.PositiveIntegerField(default=1)
    title = models.CharField(blank=False, max_length=255)
    resource_url = models.URLField()

    campaign = models.ForeignKey(
        Campaign, on_delete=models.CASCADE, blank=True, null=True
    )
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, blank=True, null=True)

    def __str__(self):
        return self.title


class Project(MetricsModelMixin("project"), models.Model):
    objects = PublicationQuerySet.as_manager()

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)

    published = models.BooleanField(default=False, blank=True, db_index=True)

    title = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, allow_unicode=True)
    thumbnail_image = models.ImageField(
        upload_to="project-thumbnails", blank=True, null=True
    )

    description = models.TextField(blank=True)
    metadata = JSONField(default=metadata_default, blank=True, null=True)

    topics = models.ManyToManyField(Topic)

    class Meta:
        unique_together = (("slug", "campaign"),)
        ordering = ["title"]
        indexes = [models.Index(fields=["id", "campaign", "published"])]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse(
            "transcriptions:project-detail",
            kwargs={"campaign_slug": self.campaign.slug, "slug": self.slug},
        )


class Item(MetricsModelMixin("item"), models.Model):
    objects = PublicationQuerySet.as_manager()

    project = models.ForeignKey(Project, on_delete=models.CASCADE)

    published = models.BooleanField(default=False, blank=True)

    title = models.CharField(max_length=600)
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
        indexes = [models.Index(fields=["project", "published"])]

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


class AssetQuerySet(PublicationQuerySet):
    def add_contribution_counts(self):
        """Add annotations for the number of transcriptions & users"""

        return self.annotate(
            transcription_count=Count("transcription", distinct=True),
            transcriber_count=Count("transcription__user", distinct=True),
            reviewer_count=Count("transcription__reviewed_by", distinct=True),
        )


class Asset(MetricsModelMixin("asset"), models.Model):
    objects = AssetQuerySet.as_manager()

    item = models.ForeignKey(Item, on_delete=models.CASCADE)

    published = models.BooleanField(default=False, blank=True, db_index=True)

    title = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, allow_unicode=True)

    description = models.TextField(blank=True)
    # TODO: do we really need this given that we import in lock-step sequence
    #       numbers with a fixed extension?
    media_url = models.TextField("Path component of the URL", max_length=255)
    media_type = models.CharField(
        max_length=4, choices=MediaType.CHOICES, db_index=True
    )
    sequence = models.PositiveIntegerField(default=1)
    year = models.CharField(blank=True, max_length=50)

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
        db_index=True,
    )

    difficulty = models.PositiveIntegerField(default=0, blank=True, null=True)

    class Meta:
        unique_together = (("slug", "item"),)
        indexes = [
            models.Index(fields=["id", "item", "published", "transcription_status"]),
            models.Index(fields=["published", "transcription_status"]),
        ]

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

    def latest_transcription(self):
        return self.transcription_set.order_by("-pk").first()


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

    class Meta:
        indexes = [
            models.Index(fields=["asset", "user"]),
        ]

    def __str__(self):
        return f"Transcription #{self.pk}"

    def clean(self):
        if (
            self.user
            and self.reviewed_by
            and self.user == self.reviewed_by
            and self.accepted
        ):
            raise ValidationError("Transcriptions cannot be self-accepted")
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

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    reservation_token = models.CharField(max_length=50)

    created_on = models.DateTimeField(editable=False, auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
    tombstoned = models.BooleanField(default=False, blank=True, null=True)


class SimpleContentBlock(models.Model):
    created_on = models.DateTimeField(editable=False, auto_now_add=True)
    updated_on = models.DateTimeField(editable=False, auto_now=True)

    slug = models.SlugField(
        unique=True,
        max_length=255,
        help_text="Label that templates use to retrieve this block",
    )

    body = models.TextField()

    def __str__(self):
        return f"SimpleContentBlock: {self.slug}"


class SimplePage(models.Model):
    created_on = models.DateTimeField(editable=False, auto_now_add=True)
    updated_on = models.DateTimeField(editable=False, auto_now=True)

    path = models.CharField(
        max_length=255,
        help_text="URL path where this page will be accessible from",
        validators=[RegexValidator(r"^/.+/$")],
    )

    title = models.CharField(max_length=200)

    body = models.TextField()

    def __str__(self):
        return f"SimplePage: {self.path}"


class CarouselSlide(models.Model):
    objects = PublicationQuerySet.as_manager()

    created_on = models.DateTimeField(editable=False, auto_now_add=True)
    updated_on = models.DateTimeField(editable=False, auto_now=True)

    ordering = models.IntegerField(
        default=0, help_text="Sort order: lower values will be listed first"
    )
    published = models.BooleanField(default=False, blank=True)

    overlay_position = models.CharField(max_length=5, choices=OverlayPosition.CHOICES)

    headline = models.CharField(max_length=255, blank=False)
    body = models.TextField(blank=True)
    image_alt_text = models.TextField(blank=True)

    carousel_image = models.ImageField(
        upload_to="carousel-slides", blank=True, null=True
    )

    lets_go_url = models.CharField(max_length=255)

    def __str__(self):
        return f"CarouselSlide: {self.headline}"


class SiteReport(models.Model):
    created_on = models.DateTimeField(editable=False, auto_now_add=True)
    campaign = models.ForeignKey(
        Campaign, on_delete=models.SET_NULL, blank=True, null=True
    )
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, blank=True, null=True)
    assets_total = models.IntegerField(blank=True, null=True)
    assets_published = models.IntegerField(blank=True, null=True)
    assets_not_started = models.IntegerField(blank=True, null=True)
    assets_in_progress = models.IntegerField(blank=True, null=True)
    assets_waiting_review = models.IntegerField(blank=True, null=True)
    assets_completed = models.IntegerField(blank=True, null=True)
    assets_unpublished = models.IntegerField(blank=True, null=True)
    items_published = models.IntegerField(blank=True, null=True)
    items_unpublished = models.IntegerField(blank=True, null=True)
    projects_published = models.IntegerField(blank=True, null=True)
    projects_unpublished = models.IntegerField(blank=True, null=True)
    anonymous_transcriptions = models.IntegerField(blank=True, null=True)
    transcriptions_saved = models.IntegerField(blank=True, null=True)
    distinct_tags = models.IntegerField(blank=True, null=True)
    tag_uses = models.IntegerField(blank=True, null=True)
    campaigns_published = models.IntegerField(blank=True, null=True)
    campaigns_unpublished = models.IntegerField(blank=True, null=True)
    users_registered = models.IntegerField(blank=True, null=True)
    users_activated = models.IntegerField(blank=True, null=True)

    class Meta:
        ordering = ("created_on",)

    # We have several places where these are exported as CSV/Excel. By default
    # the ORM will be told to retrieve these fields & lookups:
    DEFAULT_EXPORT_FIELDNAMES = [
        "created_on",
        "campaign__title",
        "assets_total",
        "assets_published",
        "assets_not_started",
        "assets_in_progress",
        "assets_waiting_review",
        "assets_completed",
        "assets_unpublished",
        "items_published",
        "items_unpublished",
        "projects_published",
        "projects_unpublished",
        "anonymous_transcriptions",
        "transcriptions_saved",
        "distinct_tags",
        "tag_uses",
        "campaigns_published",
        "campaigns_unpublished",
        "users_registered",
        "users_activated",
    ]
