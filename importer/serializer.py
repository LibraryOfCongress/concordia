from urllib.parse import urlsplit

from django.template.defaultfilters import slugify
from rest_framework import serializers

from importer.models import CollectionTaskDetails


class CreateCollection(serializers.Serializer):
    name = serializers.CharField()
    url = serializers.URLField()
    project = serializers.CharField()
    create_type = serializers.CharField(required=False)

    def validate(self, data):
        """
        Check that the collection and project exist or not.
        """
        create_type = urlsplit(data["url"]).path.split("/")[1]
        create_types = ["collections", "item"]
        if create_type not in create_types:
            raise serializers.ValidationError(
                "The url not belongs to collections or item"
            )
        if create_type == create_types[0]:
            try:
                CollectionTaskDetails.objects.get(
                    collection_slug=slugify(data["name"]),
                    subcollection_slug=slugify(data["project"]),
                )
            except CollectionTaskDetails.DoesNotExist:
                pass
            else:
                raise serializers.ValidationError(
                    "collection and project already exist"
                )

        data["create_type"] = create_type

        return data
