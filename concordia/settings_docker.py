import os

from .settings_template import *  # NOQA ignore=F405
from .settings_template import INSTALLED_APPS

DEBUG = os.getenv("DEBUG", "").lower() == "true"

EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"

ELASTICSEARCH_DSL_AUTOSYNC = os.getenv("ELASTICSEARCH_DSL_AUTOSYNC", False)

INSTALLED_APPS += ["django_elasticsearch_dsl"]

ELASTICSEARCH_DSL_SIGNAL_PROCESSOR = (
    "django_elasticsearch_dsl.signals.RealTimeSignalProcessor"
)
ELASTICSEARCH_DSL = {
    "default": {"hosts": os.getenv("ELASTICSEARCH_ENDPOINT", "elk:9200")}
}

# HMAC activation flow provide the two-step registration process,
# the user signs up and then completes activation via email instructions.

# This is *not* a secret for the HMAC activation workflow — see:
# https://django-registration.readthedocs.io/en/2.0.4/hmac.html#security-considerations
REGISTRATION_SALT = "django_registration"

RATELIMIT_BLOCK = os.getenv("RATELIMIT_BLOCK", "").lower() not in ("false", "0")

# Exporter attribution text for BagIt exports to LC
ATTRIBUTION_TEXT = (
    "Transcribed and reviewed by contributors participating in the "
    "By The People project at crowd.loc.gov."
)
