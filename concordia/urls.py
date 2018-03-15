import os
from django.shortcuts import render
from django.conf import settings
from django.urls import re_path, include
from django.views.generic import RedirectView, TemplateView
from django.conf.urls.static import static

from . import views

wireframe_urls = ([
    re_path(r'^$', RedirectView.as_view(url='/wireframes/page1.html')),
    re_path(r'^(page\d+.html)$', views.wireframe)    
], 'wireframes')

urlpatterns = [
    re_path(r'^$', TemplateView.as_view(template_name='home.html')),
    re_path(r'^wireframes/', include(wireframe_urls, namespace='wireframes'))
]

urlpatterns += static(
    '/wireframes/images/',
    document_root=os.path.join(settings.PROJECT_DIR, 'templates/wireframes/images'),
    show_indexes=True
)

