import os

from django.core.management.utils import get_random_secret_key

from .settings_template import *  # NOQA ignore=F405
from .settings_template import INSTALLED_APPS, LOGGING

LOGGING["handlers"]["stream"]["level"] = "INFO"
LOGGING["handlers"]["file"]["level"] = "INFO"
LOGGING["handlers"]["file"]["filename"] = "./logs/concordia-web.log"
LOGGING["handlers"]["celery"]["level"] = "INFO"
LOGGING["handlers"]["celery"]["filename"] = "./logs/concordia-celery.log"
LOGGING["loggers"]["django"]["level"] = "INFO"
LOGGING["loggers"]["celery"]["level"] = "INFO"

DEBUG = os.getenv("DEBUG", "").lower() == "true"

DJANGO_SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", get_random_secret_key())

EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"

S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
AWS_STORAGE_BUCKET_NAME = S3_BUCKET_NAME
AWS_DEFAULT_ACL = None  # Don't set an ACL on the files, inherit the bucket ACLs

MEDIA_URL = "https://%s.s3.amazonaws.com/" % S3_BUCKET_NAME

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
    "Transcribed and reviewed by volunteers participating in the "
    "By The People project at crowd.loc.gov."
)
