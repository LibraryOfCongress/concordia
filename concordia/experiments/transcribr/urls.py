from django.urls import re_path

from . import views

app_name = 'transcribr'

urlpatterns = [
    re_path(r'^$', views.TranscribrView.as_view(), name='transcribe'),
    re_path(
        r'^collection/(\d+)/$',
        views.TranscribrCollectionView.as_view(),
        name='collection'
    ),
    re_path(
        r'^collection/(\d+)/asset/(\d+)/$',
        views.TranscribrAssetView.as_view(),
        name='asset'
    ),
]


