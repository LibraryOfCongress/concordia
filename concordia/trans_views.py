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
        {"campaigns": reverse("campaign-list", request=request, format=format)}
    )


class CampaignList(viewsets.ModelViewSet):
    queryset = models.Campaign.objects.filter(is_active=1).order_by("title")
    serializer_class = serializers.CampaignListSerializer


class CampaignDetail(viewsets.ModelViewSet):
    queryset = models.Campaign.objects.order_by("title")
    serializer_class = serializers.CampaignDetailSerializer
