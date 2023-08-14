import datetime
import os.path
import time
from logging import getLogger

import pytesseract
from django.conf import settings
from django.contrib.auth.models import User
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Count, ExpressionWrapper, F, JSONField, Q
from django.db.models.functions import Round
from django.db.models.signals import post_save
from django.urls import reverse
from django.utils import timezone
from django_prometheus_metrics.models import MetricsModelMixin
from PIL import Image

logger = getLogger(__name__)

metadata_default = dict

User._meta.get_field("email").__dict__["_unique"] = True


def resource_file_upload_path(instance, filename):
    if instance.id and instance.path:
        return instance.path
    path = "cm-uploads/resources/%Y/{0}".format(filename.lower())
    return time.strftime(path)


class ConcordiaUser(User):
    # This class is a simple proxy model to add
    # additional user functionality to, without changing
    # the base User model.
    class Meta:
        proxy = True

    @property
    def email_reconfirmation_cache_key(self):
        return settings.EMAIL_RECONFIRMATION_KEY.format(id=self.id)

    def set_email_for_reconfirmation(self, email):
        cache.set(
            self.email_reconfirmation_cache_key,
            email,
            settings.EMAIL_RECONFIRMATION_TIMEOUT,
        )

    def get_email_for_reconfirmation(self):
        return cache.get(self.email_reconfirmation_cache_key)

    def delete_email_for_reconfirmation(self):
        cache.delete(self.email_reconfirmation_cache_key)

    def get_email_reconfirmation_key(self):
        email = self.get_email_for_reconfirmation()
        if email:
            return signing.dumps(obj={"username": self.get_username(), "email": email})
        else:
            raise ValueError("No email cached for reconfirmation")

    def validate_reconfirmation_email(self, email):
        return email == self.get_email_for_reconfirmation()


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


STATUS_COUNT_KEYS = {
    status: f"{status}_count" for status in TranscriptionStatus.CHOICE_MAP
}


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
    def annotated(self):
        return (
            self.annotate(
                asset_count=Count(
                    "project__item__asset",
                    filter=Q(
                        project__published=True,
                        project__item__published=True,
                        project__item__asset__published=True,
                    ),
                )
            )
            .filter(asset_count__gt=0)
            .annotate(
                **{
                    v: Count(
                        "project__item__asset",
                        filter=Q(
                            project__published=True,
                            project__item__published=True,
                            project__item__asset__published=True,
                            project__item__asset__transcription_status=k,
                        ),
                    )
                    for k, v in STATUS_COUNT_KEYS.items()
                }
            )
            # PostgreSQL does integer division when given two integers, which results
            # in the decimal results being dropped. We implicitly cast one field to
            # be a float through multiplication in order to do floating point division
            .annotate(
                completed_percent=ExpressionWrapper(
                    Round(100 * F("completed_count") * 1.0 / F("asset_count")),
                    output_field=models.FloatField(),
                ),
                needs_review_percent=ExpressionWrapper(
                    Round(100 * F("submitted_count") * 1.0 / F("asset_count")),
                    output_field=models.FloatField(),
                ),
            )
        )

    def listed(self):
        return self.filter(unlisted=False)

    def unlisted(self):
        return self.filter(unlisted=True)


class Campaign(MetricsModelMixin("campaign"), models.Model):
    class Status(models.IntegerChoices):
        ACTIVE = 1
        COMPLETED = 2
        RETIRED = 3

    objects = UnlistedPublicationQuerySet.as_manager()

    published = models.BooleanField(default=False, blank=True, db_index=True)
    unlisted = models.BooleanField(default=False, blank=True, db_index=True)
    status = models.IntegerField(choices=Status.choices, default=Status.ACTIVE)

    ordering = models.IntegerField(
        default=0, help_text="Sort order override: lower values will be listed first"
    )
    display_on_homepage = models.BooleanField(default=True)

    title = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, unique=True, allow_unicode=True)

    launch_date = models.DateField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)

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
        permissions = [
            ("retire_campaign", "Can retire campaign"),
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


class ResourceTypeQuerySet(models.QuerySet):
    def related_links(self):
        return self.filter(resource_type=Resource.ResourceType.RELATED_LINK)

    def completed_transcription_links(self):
        return self.filter(
            resource_type=Resource.ResourceType.COMPLETED_TRANSCRIPTION_LINK
        )


class Resource(MetricsModelMixin("resource"), models.Model):
    class ResourceType(models.IntegerChoices):
        RELATED_LINK = 1
        COMPLETED_TRANSCRIPTION_LINK = 2

    objects = ResourceTypeQuerySet.as_manager()

    sequence = models.PositiveIntegerField(default=1)
    title = models.CharField(blank=False, max_length=255)
    resource_type = models.IntegerField(
        choices=ResourceType.choices, default=ResourceType.RELATED_LINK
    )
    resource_url = models.URLField()

    campaign = models.ForeignKey(
        Campaign, on_delete=models.CASCADE, blank=True, null=True
    )
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, blank=True, null=True)

    class Meta:
        ordering = ("sequence",)

    def __str__(self):
        return self.title


class ResourceFile(models.Model):
    name = models.CharField(blank=False, max_length=255)
    path = models.CharField(blank=True, default="", max_length=255)
    resource = models.FileField(upload_to=resource_file_upload_path)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.id and not self.path:
            self.path = self.resource.name
            self.save()

    def delete(self, *args, **kwargs):
        storage = self.resource.storage

        if storage.exists(self.resource.name):
            self.resource.delete(save=False)

        super().delete(*args, **kwargs)


class Project(MetricsModelMixin("project"), models.Model):
    objects = PublicationQuerySet.as_manager()

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)

    published = models.BooleanField(default=False, blank=True, db_index=True)
    ordering = models.IntegerField(
        default=0, help_text="Sort order override: lower values will be listed first"
    )
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
        permissions = [
            ("reopen_asset", "Can reopen asset"),
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

    def get_storage_path(self, filename):
        s3_relative_path = "/".join(
            [
                self.item.project.campaign.slug,
                self.item.project.slug,
                self.item.item_id,
            ]
        )
        filename = self.media_url
        return os.path.join(s3_relative_path, filename)

    storage_image = models.ImageField(
        upload_to=get_storage_path, max_length=255, blank=True, null=True
    )

    def get_ocr_transcript(self):
        return pytesseract.image_to_string(Image.open(self.storage_image))

    def get_contributor_count(self):
        transcriptions = Transcription.objects.filter(asset=self)
        reviewer_ids = (
            transcriptions.exclude(reviewed_by__isnull=True)
            .values_list("reviewed_by", flat=True)
            .distinct()
        )
        transcriber_ids = transcriptions.values_list("user", flat=True).distinct()
        user_ids = list(set(list(reviewer_ids) + list(transcriber_ids)))
        return len(user_ids)


class Tag(MetricsModelMixin("tag"), models.Model):
    TAG_VALIDATOR = RegexValidator(r"^[- _À-ž'\w]{1,50}$")
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


class TranscriptionManager(models.Manager):
    def review_actions(self, start, end=None):
        q_accepted = Q(accepted__gte=start)
        q_rejected = Q(rejected__gte=start)
        if end is not None:
            q_accepted &= Q(accepted__lte=end)
            q_rejected &= Q(rejected__lte=end)
        return self.filter(q_accepted | q_rejected)

    def recent_review_actions(self):
        ONE_DAY_AGO = timezone.now() - datetime.timedelta(days=1)
        return self.review_actions(ONE_DAY_AGO)


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

    # ocr tracking
    ocr_generated = models.BooleanField(
        default=False,
        help_text="Flags transcription as generated directly by OCR",
    )
    ocr_originated = models.BooleanField(
        default=False,
        help_text="Flags transcription as originated from an OCR transcription",
    )

    objects = TranscriptionManager()

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


def on_transcription_save(sender, instance, **kwargs):
    if kwargs["created"]:
        user = instance.user
        attr_name = "transcribe_count"
    elif instance.reviewed_by:
        user = instance.reviewed_by
        attr_name = "review_count"
    else:
        user = None
        attr_name = None

    if user is not None and attr_name is not None:
        user_profile_activity, created = UserProfileActivity.objects.get_or_create(
            user=user,
            campaign=instance.asset.item.project.campaign,
        )
        if created:
            setattr(user_profile_activity, attr_name, 1)
        else:
            setattr(user_profile_activity, attr_name, F(attr_name) + 1)
        q = Q(transcription__user=user) | Q(transcription__reviewed_by=user)
        user_profile_activity.asset_count = (
            Asset.objects.filter(q)
            .filter(item__project__campaign=instance.asset.item.project.campaign)
            .distinct()
            .count()
        )
        user_profile_activity.save()


post_save.connect(on_transcription_save, sender=Transcription)


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


class Banner(models.Model):
    created_on = models.DateTimeField(editable=False, auto_now_add=True)
    updated_on = models.DateTimeField(editable=False, auto_now=True)

    slug = models.SlugField(max_length=80, unique=True, allow_unicode=True)
    text = models.CharField(max_length=255)
    link = models.CharField(max_length=255)
    open_in_new_window_tab = models.BooleanField(default=True, blank=True)
    active = models.BooleanField(default=False, blank=True)
    DANGER = "DANGER"
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARN = "WARN"
    ALERT_STATUS_CHOICES = [
        ("DANGER", "Red"),
        ("INFO", "Blue"),
        ("SUCCESS", "Green"),
        ("WARNING", "Grey"),
    ]
    alert_status = models.CharField(
        max_length=7,
        choices=ALERT_STATUS_CHOICES,
        default=SUCCESS,
        verbose_name="Color",
    )

    def __str__(self):
        return f"Banner: {self.slug}"

    def alert_class(self):
        return "alert-" + self.alert_status.lower()

    def btn_class(self):
        return "btn-" + self.alert_status.lower()


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
    class ReportName(models.TextChoices):
        TOTAL = "Active and completed campaigns", "Active and completed campaigns"
        RETIRED_TOTAL = "Retired campaigns", "Retired campaigns"

    created_on = models.DateTimeField(editable=False, auto_now_add=True)
    report_name = models.CharField(
        max_length=80, blank=True, default="", choices=ReportName.choices
    )
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
    daily_review_actions = models.IntegerField(blank=True, null=True)
    distinct_tags = models.IntegerField(blank=True, null=True)
    tag_uses = models.IntegerField(blank=True, null=True)
    campaigns_published = models.IntegerField(blank=True, null=True)
    campaigns_unpublished = models.IntegerField(blank=True, null=True)
    users_registered = models.IntegerField(blank=True, null=True)
    users_activated = models.IntegerField(blank=True, null=True)
    registered_contributors = models.IntegerField(blank=True, null=True)
    daily_active_users = models.IntegerField(blank=True, null=True)

    class Meta:
        ordering = ("-created_on",)

    # We have several places where these are exported as CSV/Excel. By default
    # the ORM will be told to retrieve these fields & lookups:
    DEFAULT_EXPORT_FIELDNAMES = [
        "created_on",
        "report_name",
        "campaign__title",
        "topic__title",
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
        "daily_review_actions",
        "distinct_tags",
        "tag_uses",
        "campaigns_published",
        "campaigns_unpublished",
        "users_registered",
        "users_activated",
        "registered_contributors",
        "daily_active_users",
    ]


class UserProfileActivity(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="User Id")
    campaign = models.ForeignKey(
        Campaign, on_delete=models.CASCADE, verbose_name="Campaign Id"
    )
    asset_count = models.IntegerField(default=0)
    asset_tag_count = models.IntegerField(default=0)
    transcribe_count = models.IntegerField(
        default=0, verbose_name="transcription save/submit count"
    )
    review_count = models.IntegerField(
        default=0, verbose_name="transcription review count"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "campaign"], name="user_campaign_count"
            )
        ]
        verbose_name_plural = "User profile activities"

    def __str__(self):
        return f"{self.user} - {self.campaign}"

    def get_status(self):
        display = [None, "Active", "Completed", "Retired"]
        return display[self.campaign.status]

    def total_actions(self):
        transcribe_count = self.transcribe_count or 0
        review_count = self.review_count or 0
        return transcribe_count + review_count


class CampaignRetirementProgress(models.Model):
    campaign = models.OneToOneField(Campaign, on_delete=models.CASCADE)
    project_total = models.IntegerField(default=0)
    projects_removed = models.IntegerField(default=0)
    item_total = models.IntegerField(default=0)
    items_removed = models.IntegerField(default=0)
    asset_total = models.IntegerField(default=0)
    assets_removed = models.IntegerField(default=0)
    complete = models.BooleanField(default=False)
    started_on = models.DateTimeField(auto_now_add=True)
    completed_on = models.DateTimeField(null=True)
    removal_log = models.JSONField(default=list)

    def __str__(self):
        return f"Removal progress for {self.campaign}"
