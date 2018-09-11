from urllib.parse import urlsplit

from django.template.defaultfilters import slugify
from rest_framework import serializers

from importer.models import CampaignTaskDetails


class CreateCampaign(serializers.Serializer):
    name = serializers.CharField()
    url = serializers.URLField()
    project = serializers.CharField()
    create_type = serializers.CharField(required=False)

    def validate(self, data):
        """
        Check that the campaign and project exist or not.
        """
        create_type = urlsplit(data["url"]).path.split("/")[1]
        create_types = ["collections", "search", "item"]
        if create_type not in create_types:
            raise serializers.ValidationError(
                "The url not belongs to campaigns or item"
            )
        if create_type == create_types[0] or create_type == create_types[1]:
            try:
                CampaignTaskDetails.objects.get(
                    campaign_slug=slugify(data["name"]),
                    project_slug=slugify(data["project"]),
                )
            except CampaignTaskDetails.DoesNotExist:
                pass
            else:
                raise serializers.ValidationError("campaign and project already exist")

        data["create_type"] = create_type

        return data
