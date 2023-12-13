from django.apps.config import AppConfig
from django.contrib.admin.apps import AdminConfig
from django.contrib.staticfiles.apps import StaticFilesConfig


class ConcordiaAppConfig(AppConfig):
    name = "concordia"

    def ready(self):
        from .signals import handlers  # NOQA


class ConcordiaAdminConfig(AdminConfig):
    default_site = "concordia.admin_site.ConcordiaAdminSite"

    def ready(self):
        self.module.autodiscover()


class ConcordiaStaticFilesConfig(StaticFilesConfig):
    ignore_patterns = ["scss", "js/src/*"]
