import os

from .settings_template import *  # NOQA ignore=F405
from .settings_template import INSTALLED_APPS

DEBUG = os.getenv("DEBUG", "").lower() == "true"

EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"

INSTALLED_APPS += ["django_opensearch_dsl"]

# Globally disable auto-syncing
OPENSEARCH_DSL_AUTOSYNC = os.getenv("OPENSEARCH_DSL_AUTOSYNC", False)

OPENSEARCH_DSL = {
    "default": {"hosts": os.getenv("OPENSEARCH_ENDPOINT", "9200:9200")},
    "secure": {
        "hosts": [
            {"scheme": "https", "host": os.getenv("OPENSEARCH_ENDPOINT"), "port": 9201}
        ],
        "http_auth": ("admin", "admin"),
        "timeout": 120,
    },
}


# HMAC activation flow provide the two-step registration process,
# the user signs up and then completes activation via email instructions.

# This is *not* a secret for the HMAC activation workflow — see:
# https://django-registration.readthedocs.io/en/2.0.4/hmac.html#security-considerations
REGISTRATION_SALT = "django_registration"

RATELIMIT_BLOCK = os.getenv("RATELIMIT_BLOCK", "").lower() not in ("false", "0")
