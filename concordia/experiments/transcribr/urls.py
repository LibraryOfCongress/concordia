from django.urls import re_path

from . import views

app_name = 'transcribr'

urlpatterns = [
    re_path(r'^$', views.TranscribrView.as_view(), name='transcribe'),
]


