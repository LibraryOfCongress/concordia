import logging
import os

import structlog

from .settings_template import *  # NOQA ignore=F405
from .settings_template import DATABASES

DEBUG = False

DATABASES["default"].update({"PASSWORD": "", "USER": "postgres"})

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "default-location",
    },
    "view_cache": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "view-location",
    },
    "configuration_cache": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "configuration-location",
    },
    "visualization_cache": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "visualization-location",
    },
}

structlog.configure(
    processors=[],
    wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL),
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

# These cause Celery to run tasks locally, synchronously and immediately
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

DEFAULT_TO_EMAIL = "rsar@loc.gov"
CONCORDIA_DEVS = [
    "rsar@loc.gov",
]

ALLOWED_HOSTS = ["127.0.0.1", "0.0.0.0"]  # nosec

EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"

SESSION_ENGINE = "django.contrib.sessions.backends.cache"

RATELIMIT_ENABLE = False

# Turnstile settings
TURNSTILE_JS_API_URL = os.environ.get(
    "TURNSTILE_JS_API_URL", "https://challenges.cloudflare.com/turnstile/v0/api.js"
)
TURNSTILE_VERIFY_URL = os.environ.get(
    "TURNSTILE_VERIFY_URL", "https://challenges.cloudflare.com/turnstile/v0/siteverify"
)
TURNSTILE_SITEKEY = os.environ.get(
    "TURNSTILE_SITEKEY", "1x00000000000000000000BB"
)  # Always pass, invisible
TURNSTILE_SECRET = os.environ.get(
    "TURNSTILE_SECRET", "1x0000000000000000000000000000000AA"
)  # Always pass

CONCORDIA_DEVS = []
