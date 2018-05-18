
import os
import sys

from django.conf import settings
from django.contrib import admin
from django.urls import re_path, include
from django.conf.urls.static import static
from django.views.generic import TemplateView
from django.contrib.auth import views as auth_views
from django.views.static import serve

from machina.app import board

from machina.app import board

from . import views
from . import trans_urls
from faq.views import FAQView

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(PROJECT_DIR)

sys.path.append(BASE_DIR)

sys.path.append(os.path.join(BASE_DIR, 'config'))
from config import Config
# TODO: use util to import Config

for key, value in getattr(settings, 'ADMIN_SITE', {}).items():
    setattr(admin.site, key, value)


tx_urlpatterns = ([
    re_path(r'^$', views.TranscribrView.as_view(), name='transcribe'),
    re_path(
        r'^create/$',
        views.CollectionView.as_view(),
        name='create'
    ),
    re_path(
        r'^([^/]+)/$',
        views.TranscribrCollectionView.as_view(),
        name='collection'
    ),
    re_path(
        r'export/([^/]+)/$',
        views.ExportCollectionView.as_view(),
        name='export collection'
    ),
    re_path(
        r'delete/([^/]+)/$',
        views.DeleteCollectionView.as_view(),
        name='delete collection'
    ),
    re_path(
        r'report/([^/]+)/$',
        views.ReportCollectionView.as_view(),
        name='report collection'
    ),
    re_path(
        r'^([^/]+)/asset/([^/]+)/$',
        views.TranscribrAssetView.as_view(),
        name='asset'
    ),
    re_path(
        r'transcription/(\d+)/$',
        views.TranscriptionView.as_view(),
        name='transcription'
    )

], 'transcriptions')

urlpatterns = [
    re_path(r'^$', TemplateView.as_view(template_name='home.html')),
    re_path(r'^about/$', TemplateView.as_view(template_name='about.html'), name='about'),
    re_path(r'^transcribe/', include(tx_urlpatterns, namespace='transcriptions')),
    re_path(r'^api/v1/', include(trans_urls)),

    re_path(
        r'^account/register/$',
        views.ConcordiaRegistrationView.as_view(),
        name='registration_register',
    ),
    re_path(r'^account/profile/$', views.AccountProfileView.as_view(), name='user-profile'),
    re_path(r'^account/', include(Config.Get('REGISTRATION_URLS'))),
    re_path(r'^experiments/(.+)/$', views.ExperimentsView.as_view(), name='experiments'),
    re_path(r'^wireframes/', include('concordia.experiments.wireframes.urls')),

    re_path(r'^privacy-policy/$', TemplateView.as_view(template_name='policy.html'), name='privacy-policy'),
    re_path(r'^cookie-policy/$', TemplateView.as_view(template_name='policy.html'), name='cookie-policy'),
    re_path(r'^faq/$', FAQView.as_view(), name='faq'),
    re_path(r'^legal/$', TemplateView.as_view(template_name='legal.html'), name='legal'),

    re_path(r'^admin/', admin.site.urls),

    # Apps
    re_path(r'^forum/', include(board.urls))
]

urlpatterns += [
    re_path(r'^password_reset/$', auth_views.password_reset, name='password_reset'),
    re_path(r'^password_reset/done/$', auth_views.password_reset_done, name='password_reset_done'),
    re_path(r'^reset/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
        auth_views.password_reset_confirm, name='password_reset_confirm'),
    re_path(r'^reset/done/$', auth_views.password_reset_complete, name='password_reset_complete'),
]

urlpatterns += [
        re_path(r'^static/(?P<path>.*)$', serve, {
            'document_root': settings.STATIC_ROOT,
        }),
]

urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {
            'document_root': settings.MEDIA_ROOT,
        }),
]
