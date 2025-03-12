from __future__ import absolute_import, unicode_literals

from celery import Celery
from celery.signals import setup_logging

app = Celery("importer")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")


# Celery won't be default use the logging settings
# This configures Celery's logging to use our settings
@setup_logging.connect
def configure_logging(**kwargs):
    import logging.config

    from django.conf import settings

    logging.config.dictConfig(settings.LOGGING)


# Load task modules from all registered Django app configs.
app.autodiscover_tasks()
