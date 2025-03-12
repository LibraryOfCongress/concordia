from __future__ import absolute_import, unicode_literals

import os

import sentry_sdk
from celery import Celery
from celery.signals import setup_logging
from sentry_sdk.integrations.celery import CeleryIntegration

from concordia.version import get_concordia_version

SENTRY_BACKEND_DSN = os.environ.get("SENTRY_BACKEND_DSN", None)

if SENTRY_BACKEND_DSN:
    CONCORDIA_ENVIRONMENT = os.environ.get("CONCORDIA_ENVIRONMENT", None)
    sentry_sdk.init(
        SENTRY_BACKEND_DSN,
        environment=CONCORDIA_ENVIRONMENT,
        release=get_concordia_version(),
        integrations=[CeleryIntegration()],
    )

app = Celery("concordia")

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
