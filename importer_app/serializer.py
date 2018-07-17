
from rest_framework import serializers


class CreateCollection(serializers.Serializer):
    name = serializers.SlugField()
    url = serializers.URLField()
    create_type = serializers.CharField()

