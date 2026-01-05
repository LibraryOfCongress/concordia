import os
import sys

from .settings_template import *  # NOQA ignore=F405
from .settings_template import DATABASES, LOGGING, STORAGES

DEBUG = False
RATELIMIT_ENABLE = False

# Load testing DB name standard. If you need a different DB name, create a
# personal settings file (eg settings_loadtest_<username>.py) and override it
# there.
DATABASES["default"]["NAME"] = "concordia_lt"

# Ensure Turnstile does not block Locust. Default to Cloudflare's test keys that
# always pass, but allow env vars to override.
TURNSTILE_SITEKEY = os.environ.get(
    "TURNSTILE_SITEKEY",
    "1x00000000000000000000BB",  # always pass, invisible
)
TURNSTILE_SECRET = os.environ.get(
    "TURNSTILE_SECRET",
    "1x0000000000000000000000000000000AA",  # always pass
)

LOGGING["handlers"]["stream"]["level"] = "INFO"
LOGGING["handlers"]["file"]["level"] = "INFO"
LOGGING["handlers"]["celery"]["level"] = "INFO"
LOGGING["handlers"]["console"] = {
    "level": "INFO",
    "class": "logging.StreamHandler",
    "stream": sys.stdout,
}
LOGGING["handlers"]["celery_console"] = {
    "level": "INFO",
    "class": "logging.StreamHandler",
    "stream": sys.stdout,
    "formatter": "long",
}
LOGGING["handlers"]["structlog_file"]["level"] = "INFO"
LOGGING["handlers"]["structlog_console"]["level"] = "INFO"

LOGGING["loggers"]["django"]["handlers"] = ["file", "stream", "console"]
LOGGING["loggers"]["celery"]["handlers"] = ["celery", "celery_console"]
LOGGING["loggers"]["concordia"]["handlers"] = ["file", "stream", "console"]
LOGGING["loggers"]["concordia"]["level"] = "INFO"
LOGGING["loggers"]["django.utils.autoreload"] = {"level": "INFO"}
LOGGING["loggers"]["django.template"] = {"level": "INFO"}
LOGGING["loggers"]["structlog"]["handlers"] = ["structlog_file", "structlog_console"]
LOGGING["loggers"]["django_structlog"]["handlers"] = [
    "structlog_file",
    "structlog_console",
]

ALLOWED_HOSTS = ["127.0.0.1", "0.0.0.0", "*"]  # nosec

MAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
EMAIL_FILE_PATH = "/tmp/concordia-messages"  # nosec
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "test@example.test")
DEFAULT_TO_EMAIL = DEFAULT_FROM_EMAIL

REGISTRATION_SALT = "django_registration"  # doesn't need to be secret

S3_BUCKET_NAME = "crowd-staging-content"
EXPORT_S3_BUCKET_NAME = "crowd-staging-export"
STORAGES = {
    **STORAGES,
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
    },
    "assets": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            "querystring_auth": False,
        },
    },
    "visualizations": {
        "BACKEND": "concordia.storage_backends.OverwriteS3Boto3Storage",
        "OPTIONS": {
            "querystring_auth": False,
        },
    },
}

AWS_STORAGE_BUCKET_NAME = S3_BUCKET_NAME
AWS_DEFAULT_ACL = None  # Don't set an ACL on the files, inherit the bucket ACLs
MEDIA_URL = "https://%s.s3.amazonaws.com/" % S3_BUCKET_NAME

SECURE_CROSS_ORIGIN_OPENER_POLICY = None
