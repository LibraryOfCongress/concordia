from django.urls import re_path
from rest_framework.documentation import include_docs_urls
from rest_framework.schemas import get_schema_view

from . import trans_views as views

api_title = "Concordia API"
api_description = "A Web API for transcribing and tagging collections."
schema_view = get_schema_view(title=api_title)


urlpatterns = [
    re_path("^$", views.api_root),
    re_path(
        r"^collections/$",
        views.CollectionList.as_view({"get": "list", "post": "create"}),
        name="collection-list",
    ),
    re_path(
        r"^collections/(?P<pk>\d+)/$",
        views.CollectionDetail.as_view({"get": "retrieve", "put": "update"}),
        name="collection-detail",
    ),
    re_path(r"^schema/$", schema_view),
    re_path(r"^docs/", include_docs_urls(title=api_title, description=api_description)),
]
