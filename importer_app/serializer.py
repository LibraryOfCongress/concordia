
from rest_framework import serializers


class CreateCollection(serializers.Serializer):
    collection_name = serializers.SlugField()
    collection_url = serializers.URLField()

