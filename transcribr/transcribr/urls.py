from django.urls import re_path, include
from rest_framework import routers
from rest_framework.schemas import get_schema_view
from rest_framework.documentation import include_docs_urls

from . import views

api_title = 'Transcribr API'
api_description = 'A Web API for transcribing and tagging LoC collections.'
schema_view = get_schema_view(title=api_title)

router = routers.DefaultRouter()
router.register(r'collections', views.CollectionListViewSet)

urlpatterns = [
    re_path(r'^', include(router.urls)),
    re_path(r'^schema/$', schema_view),
    re_path(
        r'^docs/',
        include_docs_urls(title=api_title, description=api_description)
    )
]
