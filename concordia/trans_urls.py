from django.urls import re_path
from rest_framework.documentation import include_docs_urls
from rest_framework.schemas import get_schema_view

from . import trans_views as views

api_title = "Concordia API"
api_description = "A Web API for transcribing and tagging campaigns."
schema_view = get_schema_view(title=api_title)


urlpatterns = [
    re_path("^$", views.api_root),
    re_path(
        r"^campaigns/$",
        views.CampaignList.as_view({"get": "list", "post": "create"}),
        name="campaign-list",
    ),
    re_path(
        r"^campaigns/(?P<pk>\d+)/$",
        views.CampaignDetail.as_view({"get": "retrieve", "put": "update"}),
        name="campaign-detail",
    ),
    re_path(r"^schema/$", schema_view),
    re_path(r"^docs/", include_docs_urls(title=api_title, description=api_description)),
]
