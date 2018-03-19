from django.urls import re_path, include
from django.views.generic import TemplateView


urlpatterns = [
    re_path(r'^$', TemplateView.as_view(template_name='home.html')),
    re_path(r'^wireframes/', include(wireframe_urls, namespace='wireframes'))
]


