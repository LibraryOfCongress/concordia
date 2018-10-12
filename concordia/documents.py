from django.contrib.auth.models import User
from django_elasticsearch_dsl import fields, DocType, Index

from .models import Transcription, UserAssetTagCollection


user = Index("users")
user.settings(number_of_shards=1, number_of_replicas=0)

tag_collection = Index("tags")
tag_collection.settings(number_of_shards=1, number_of_replicas=0)

transcription = Index("transcriptions")
transcription.settings(number_of_shards=1, number_of_replicas=0)


@user.doc_type
class UserDocument(DocType):
    class Meta:
        model = User

        fields = ["last_login", "date_joined"]


@tag_collection.doc_type
class TagCollectionDocument(DocType):
    tags = fields.TextField(attr="tags_to_string")
    asset = fields.ObjectField(
        properties={"title": fields.TextField(), "resource_id": fields.TextField()}
    )

    class Meta:
        model = UserAssetTagCollection
        fields = ["created_on", "updated_on"]


@transcription.doc_type
class TranscriptionDocument(DocType):
    class Meta:
        model = Transcription

        fields = [
            "created_on",
            "updated_on",
            "text",
            "accepted",
            "rejected",
            "submitted",
        ]

