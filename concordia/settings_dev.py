import os

from .settings_template import *

LOGGING["handlers"]["stream"]["level"] = "DEBUG"
LOGGING["handlers"]["file"]["level"] = "DEBUG"
LOGGING["handlers"]["file"]["filename"] = "./logs/concordia-web.log"
LOGGING["handlers"]["celery"]["level"] = "DEBUG"
LOGGING["handlers"]["celery"]["filename"] = "./logs/concordia-celery.log"
LOGGING["loggers"]["django"]["level"] = "DEBUG"
LOGGING["loggers"]["celery"]["level"] = "DEBUG"

DEBUG = True

DATABASES["default"]["PORT"] = "54323"

ALLOWED_HOSTS = ["127.0.0.1", "0.0.0.0", "*"]

CELERY_BROKER_URL = "pyamqp://guest@localhost"
CELERY_RESULT_BACKEND = "rpc://"

S3_BUCKET_NAME = "crowd-dev-content"

DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
AWS_STORAGE_BUCKET_NAME = S3_BUCKET_NAME
AWS_DEFAULT_ACL = None  # Don't set an ACL on the files, inherit the bucket ACLs

MEDIA_URL = "https://%s.s3.amazonaws.com/" % S3_BUCKET_NAME

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
EMAIL_FILE_PATH = "/tmp/concordia-messages"  # change this to a proper location
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "")
DEFAULT_TO_EMAIL = DEFAULT_FROM_EMAIL

ELASTICSEARCH_DSL_AUTOSYNC = False

ELASTICSEARCH_DSL_SIGNAL_PROCESSOR = (
    "django_elasticsearch_dsl.signals.RealTimeSignalProcessor"
)
ELASTICSEARCH_DSL = {"default": {"hosts": "localhost:9200"}}

INSTALLED_APPS += ["django_elasticsearch_dsl"]

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

REGISTRATION_SALT = "django_registration"  # doesn't need to be secret

INSTALLED_APPS += ["debug_toolbar"]
MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]
INTERNAL_IPS = ("127.0.0.1",)

INSTALLED_APPS += ("django_extensions",)
SHELL_PLUS_PRE_IMPORTS = [
    ("concordia.views", "get_anonymous_user"),
    ("concordia.models", "TranscriptionStatus"),
]

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
