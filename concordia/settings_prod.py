import os

from .settings_template import *

LOGGING["handlers"]["stream"]["level"] = "INFO"
LOGGING["handlers"]["file"]["level"] = "INFO"
LOGGING["handlers"]["file"]["filename"] = "./logs/concordia-web.log"
LOGGING["handlers"]["celery"]["level"] = "INFO"
LOGGING["handlers"]["celery"]["filename"] = "./logs/concordia-celery.log"
LOGGING["loggers"]["django"]["level"] = "INFO"
LOGGING["loggers"]["celery"]["level"] = "INFO"

DJANGO_SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "changeme")

# TODO: For final deployment to production,
# when we are running https, uncomment this next line
# CSRF_COOKIE_SECURE = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "concordia",
        "USER": "concordia",
        "PASSWORD": os.getenv("POSTGRESQL_PW"),
        "HOST": os.getenv("POSTGRESQL_HOST", "db"),
        "PORT": "5432",
    }
}

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "pyamqp://guest@rabbit:5672")
CELERY_RESULT_BACKEND = "rpc://"

DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
STATICFILES_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
AWS_STORAGE_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
AWS_DEFAULT_ACL = None  # Don't set an ACL on the files, inherit the bucket ACLs

ELASTICSEARCH_DSL_AUTOSYNC = False

INSTALLED_APPS += ["django_elasticsearch_dsl"]

ELASTICSEARCH_DSL_SIGNAL_PROCESSOR = (
    "django_elasticsearch_dsl.signals.RealTimeSignalProcessor"
)
ELASTICSEARCH_DSL = {
    "default": {"hosts": os.getenv("ELASTICSEARCH_ENDPOINT", "elk:9200")}
}

EMAIL_USE_TLS = True
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_PORT = 587
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "crowd@loc.gov")
DEFAULT_TO_EMAIL = DEFAULT_FROM_EMAIL

# HMAC activation flow provide the two-step registration process,
# the user signs up and then completes activation via email instructions.
REGISTRATION_URLS = "registration.backends.hmac.urls"
REGISTRATION_SALT = "registration"  # doesn't need to be secret

ACCOUNT_ACTIVATION_DAYS = 1  # required for HMAC registration two-step-flow
