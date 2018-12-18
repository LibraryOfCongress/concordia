from django.apps.config import AppConfig
from django.contrib.admin.apps import AdminConfig


class ConcordiaAppConfig(AppConfig):
    name = "concordia"

    def ready(self):
        from .signals import handlers  # NOQA


class ConcordiaAdminConfig(AdminConfig):
    default_site = "concordia.admin_site.ConcordiaAdminSite"

    def ready(self):
        self.module.autodiscover()
