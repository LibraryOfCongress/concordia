
from django.urls import re_path

from importer import views

urlpatterns = [
    re_path(
        r"^create_collection/$",
        views.CreateCollectionView.as_view(),
        name="create_collection",
    )
]
