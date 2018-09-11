
from django.urls import re_path

from importer import views

urlpatterns = [
    re_path(
        r"^create_campaign/$",
        views.CreateCampaignView.as_view(),
        name="create_campaign",
    )
]
