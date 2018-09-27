from django.apps.config import AppConfig


class ConcordiaAppConfig(AppConfig):
    name = "concordia"

    def ready(self):
        from .signals import handlers
