from logging import getLogger

from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse

from .models import Campaign, Status
from .serializers import CampaignDetailSerializer, CampaignListSerializer

logger = getLogger(__name__)


@api_view(["GET"])
def api_root(request, format=None):
    return Response(
        {"campaigns": reverse("campaign-list", request=request, format=format)}
    )


class CampaignList(viewsets.ModelViewSet):
    queryset = Campaign.objects.filter(status=Status.ACTIVE).order_by("title")
    serializer_class = CampaignListSerializer


class CampaignDetail(viewsets.ModelViewSet):
    queryset = Campaign.objects.order_by("title")
    serializer_class = CampaignDetailSerializer
