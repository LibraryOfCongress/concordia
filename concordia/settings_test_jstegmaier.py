from .settings_template import *  # NOQA ignore=F405
from .settings_template import DATABASES

DEBUG = False

DATABASES["default"]["PORT"] = "5432"

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
}

DEFAULT_TO_EMAIL = "jstegmaier@loc.gov"

ALLOWED_HOSTS = ["127.0.0.1", "0.0.0.0"]  # nosec

EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"

SESSION_ENGINE = "django.contrib.sessions.backends.cache"

RATELIMIT_ENABLE = False
