from django.contrib.auth.models import User
from django.db.models import Count
from django_elasticsearch_dsl import Document, fields
from django_elasticsearch_dsl.registries import registry

from .models import Asset, SiteReport, Transcription, UserAssetTagCollection


@registry.register_document
class UserDocument(Document):
    class Index:
        # Name of the Elasticsearch index
        name = "users"
        # See Elasticsearch Indices API reference for available settings
        settings = {"number_of_shards": 1, "number_of_replicas": 0}

    transcription_count = fields.IntegerField()

    class Django:
        model = User
        fields = ["last_login", "date_joined", "is_active", "id"]

    def prepare_transcription_count(self, instance):
        qs = User.objects.filter(id=instance.id).annotate(Count("transcription"))
        return qs[0].transcription__count


@registry.register_document
class SiteReportDocument(Document):
    class Index:
        # Name of the Elasticsearch index
        name = "site_reports"
        # See Elasticsearch Indices API reference for available settings
        settings = {"number_of_shards": 1, "number_of_replicas": 0}

    campaign = fields.ObjectField(properties={"slug": fields.KeywordField()})
    topic = fields.ObjectField(properties={"slug": fields.KeywordField()})

    class Django:
        model = SiteReport

        fields = [
            "created_on",
            "report_name",
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


@registry.register_document
class TagCollectionDocument(Document):
    class Index:
        # Name of the Elasticsearch index
        name = "tags"
        # See Elasticsearch Indices API reference for available settings
        settings = {"number_of_shards": 1, "number_of_replicas": 0}

    tags = fields.NestedField(properties={"value": fields.TextField()})
    asset = fields.ObjectField(
        properties={
            "title": fields.TextField(),
            "slug": fields.TextField(),
            "transcription_status": fields.KeywordField(),
            "item": fields.ObjectField(
                properties={
                    "item_id": fields.TextField(),
                    "project": fields.ObjectField(
                        properties={
                            "slug": fields.KeywordField(),
                            "campaign": fields.ObjectField(
                                properties={"slug": fields.KeywordField()}
                            ),
                        }
                    ),
                }
            ),
        }
    )
    user = fields.ObjectField(properties={"id": fields.IntegerField()})

    class Django:
        model = UserAssetTagCollection
        fields = ["created_on", "updated_on"]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .order_by("pk")
            .prefetch_related(
                "asset__item", "asset__item__project", "asset__item__project__campaign"
            )
        )


@registry.register_document
class TranscriptionDocument(Document):
    class Index:
        # Name of the Elasticsearch index
        name = "transcriptions"
        # See Elasticsearch Indices API reference for available settings
        settings = {"number_of_shards": 1, "number_of_replicas": 0}

    asset = fields.ObjectField(
        properties={
            "title": fields.TextField(),
            "slug": fields.TextField(),
            "transcription_status": fields.KeywordField(),
            "item": fields.ObjectField(
                properties={
                    "item_id": fields.TextField(),
                    "project": fields.ObjectField(
                        properties={
                            "slug": fields.KeywordField(),
                            "campaign": fields.ObjectField(
                                properties={"slug": fields.KeywordField()}
                            ),
                            "topics": fields.NestedField(
                                properties={"slug": fields.KeywordField()}
                            ),
                        }
                    ),
                }
            ),
        }
    )
    user = fields.ObjectField(properties={"id": fields.IntegerField()})
    reviewed_by = fields.ObjectField(properties={"id": fields.IntegerField()})
    supersedes = fields.ObjectField(properties={"id": fields.IntegerField()})

    class Django:
        model = Transcription

        fields = [
            "id",
            "created_on",
            "updated_on",
            "text",
            "accepted",
            "rejected",
            "submitted",
        ]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .order_by("pk")
            .prefetch_related(
                "asset__item",
                "asset__item__project",
                "asset__item__project__topics",
                "asset__item__project__campaign",
            )
        )


@registry.register_document
class AssetDocument(Document):
    class Index:
        # Name of the Elasticsearch index
        name = "assets"
        # See Elasticsearch Indices API reference for available settings
        settings = {"number_of_shards": 1, "number_of_replicas": 0}

    item = fields.ObjectField(
        properties={
            "item_id": fields.KeywordField(),
            "project": fields.ObjectField(
                properties={
                    "slug": fields.KeywordField(),
                    "campaign": fields.ObjectField(
                        properties={"slug": fields.KeywordField()}
                    ),
                    "topics": fields.NestedField(
                        properties={"slug": fields.KeywordField()}
                    ),
                }
            ),
        }
    )

    transcription_status = fields.KeywordField()

    latest_transcription = fields.ObjectField(
        properties={
            "created_on": fields.DateField(),
            "updated_on": fields.DateField(),
            "accepted": fields.DateField(),
            "rejected": fields.DateField(),
            "submitted": fields.DateField(),
        }
    )

    submission_count = fields.IntegerField()

    def prepare_submission_count(self, instance):
        return Transcription.objects.filter(
            asset=instance, submitted__isnull=True
        ).count()

    class Django:
        model = Asset
        fields = ["published", "difficulty", "slug", "sequence", "year"]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .order_by("pk")
            .prefetch_related(
                "item",
                "item__project",
                "item__project__topics",
                "item__project__campaign",
            )
        )
