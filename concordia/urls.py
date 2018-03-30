from django.conf import settings
from django.contrib import admin
from django.urls import re_path, include
from django.conf.urls.static import static
from django.views.generic import TemplateView

from . import views

for key, value in getattr(settings, 'ADMIN_SITE', {}).items():
    setattr(admin.site, key, value)

REGISTRATION_URLS = getattr(
    settings,
    'REGISTRATION_URLS',
    'registration.backends.simple.urls'
)


tx_urlpatterns = ([
    re_path(r'^$', views.TranscribrView.as_view(), name='transcribe'),
    re_path(
        r'^([^/]+)/$',
        views.TranscribrCollectionView.as_view(),
        name='collection'
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
    re_path(r'^api/v1/', include('transcribr.urls')),
    re_path(
        r'^account/register/$',
        views.ConcordiaRegistrationView.as_view(),
        name='registration_register',
    ),
    re_path(r'^account/profile/$', views.AccountProfileView.as_view(), name='user-profile'),
    re_path(r'^account/', include(REGISTRATION_URLS)),
    re_path(r'^experiments/(.+)/$', views.ExperimentsView.as_view(), name='experiments'),
    re_path(r'^wireframes/', include('concordia.experiments.wireframes.urls')),

    re_path(r'^privacy-policy/$', views.ToDoView.as_view(), name='privacy-policy'),
    re_path(r'^cookie-policy/$', views.ToDoView.as_view(), name='cookie-policy'),
    re_path(r'^faq/$', views.ToDoView.as_view(), name='faq'),
    re_path(r'^legal/$', views.ToDoView.as_view(), name='legal'),

    re_path(r'^admin/', admin.site.urls),
]

urlpatterns += static(
    settings.STATIC_URL,
    document_root=settings.STATIC_ROOT,
    show_indexes=True
)
