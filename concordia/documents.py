from django.contrib.auth.models import User
from django_elasticsearch_dsl import DocType, Index, fields

from .models import Asset, SiteReport, Transcription, UserAssetTagCollection

user = Index("users")
user.settings(number_of_shards=1, number_of_replicas=0)

tag_collection = Index("tags")
tag_collection.settings(number_of_shards=1, number_of_replicas=0)

transcription = Index("transcriptions")
transcription.settings(number_of_shards=1, number_of_replicas=0)

site_report = Index("site_reports")
site_report.settings(number_of_shards=1, number_of_replicas=0)

asset = Index("assets")
asset.settings(number_of_shards=1, number_of_replicas=0)


@user.doc_type
class UserDocument(DocType):
    class Meta:
        model = User

        fields = ["last_login", "date_joined", "username", "is_active"]


@site_report.doc_type
class SiteReportDocument(DocType):
    campaign = fields.ObjectField(properties={"slug": fields.KeywordField()})

    class Meta:
        model = SiteReport

        fields = [
            "created_on",
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


@tag_collection.doc_type
class TagCollectionDocument(DocType):
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
    user = fields.ObjectField(properties={"username": fields.TextField()})

    class Meta:
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


@transcription.doc_type
class TranscriptionDocument(DocType):
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
    user = fields.ObjectField(properties={"username": fields.KeywordField()})
    reviewed_by = fields.ObjectField(properties={"username": fields.KeywordField()})
    supersedes = fields.ObjectField(properties={"id": fields.IntegerField()})

    class Meta:
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
                "asset__item", "asset__item__project", "asset__item__project__campaign"
            )
        )


@asset.doc_type
class AssetDocument(DocType):
    item = fields.ObjectField(
        properties={
            "item_id": fields.KeywordField(),
            "project": fields.ObjectField(
                properties={
                    "slug": fields.KeywordField(),
                    "campaign": fields.ObjectField(
                        properties={"slug": fields.KeywordField()}
                    ),
                }
            ),
        }
    )

    transcription_status = fields.KeywordField()

    class Meta:
        model = Asset
        fields = ["published", "difficulty", "slug", "sequence", "year"]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .order_by("pk")
            .prefetch_related("item", "item__project", "item__project__campaign")
        )
