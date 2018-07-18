from logging import getLogger

from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse

from . import models, serializers

logger = getLogger(__name__)


@api_view(["GET"])
def api_root(request, format=None):
    return Response(
        {"collections": reverse("collection-list", request=request, format=format)}
    )


class CollectionList(viewsets.ModelViewSet):
    queryset = models.Collection.objects.filter(is_active=1).order_by("title")
    serializer_class = serializers.CollectionListSerializer


class CollectionDetail(viewsets.ModelViewSet):
    queryset = models.Collection.objects.order_by("title")
    serializer_class = serializers.CollectionDetailSerializer
