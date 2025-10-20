import json
import logging
import os
from time import time

from django.conf import settings
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import ListView

from concordia.models import Banner, Campaign, CarouselSlide
from concordia.version import get_concordia_version

# These imports are required to make chainted attribute access like, e.g.,
# views.campaigns.CampaignDetailView work correctly
from . import (
    accounts,  # noqa: F401
    ajax,  # noqa: F401
    assets,  # noqa: F401
    campaigns,  # noqa: F401
    items,  # noqa: F401
    maintenance_mode,  # noqa: F401
    projects,  # noqa: F401
    rate_limit,  # noqa: F401
    simple_pages,  # noqa: F401
    topics,  # noqa: F401
    visualizations,  # noqa: F401
)
from .decorators import default_cache_control

logger = logging.getLogger(__name__)


@never_cache
def healthz(request):
    status = {
        "current_time": time(),
        "load_average": os.getloadavg(),
        "debug": settings.DEBUG,
    }

    # We don't want to query a large table but we do want to hit the database
    # at last once:
    status["database_has_data"] = Campaign.objects.count() > 0

    status["application_version"] = get_concordia_version()

    return HttpResponse(content=json.dumps(status), content_type="application/json")


@method_decorator(default_cache_control, name="dispatch")
class HomeView(ListView):
    template_name = "home.html"

    queryset = (
        Campaign.objects.published()
        .listed()
        .filter(display_on_homepage=True)
        .order_by("ordering", "title")
    )
    context_object_name = "campaigns"

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data(*args, **kwargs)

        banner = Banner.objects.filter(active=True).first()

        if banner is not None:
            ctx["banner"] = banner

        ctx["slides"] = CarouselSlide.objects.published().order_by("ordering")

        if ctx["slides"]:
            ctx["firstslide"] = ctx["slides"][0]

        return ctx
