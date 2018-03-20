from django.conf import settings
from django.contrib import admin
from django.urls import re_path, include
from django.views.generic import TemplateView

from . import views

for key, value in getattr(settings, 'ADMIN_SITE', {}).items():
    setattr(admin.site, key, value)


urlpatterns = [
    re_path(r'^$', TemplateView.as_view(template_name='home.html')),
    re_path(r'^about/$', TemplateView.as_view(template_name='about.html'), name='about'),

    re_path(r'^account/register/$',
        views.ConcordiaRegistrationView.as_view(),
        name='registration_register',
    ),
    re_path(r'^account/profile/$', views.AccountProfileView.as_view(), name='user-profile'),
    # re_path(r'^account/', include('registration.backends.hmac.urls')),
    re_path(r'^account/', include('registration.backends.simple.urls')),

    re_path(r'^wireframes/', include('concordia.experiments.wireframes.urls')),
    re_path(r'^transcribe/', include('concordia.experiments.transcribr.urls')),

    re_path(r'^admin/', admin.site.urls),

]
