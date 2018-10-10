import json
import os

from .secrets import get_secret
from .settings_template import *

LOGGING["handlers"]["stream"]["level"] = "INFO"
LOGGING["handlers"]["file"]["level"] = "INFO"
LOGGING["handlers"]["file"]["filename"] = "./logs/concordia-web.log"
LOGGING["handlers"]["celery"]["level"] = "INFO"
LOGGING["handlers"]["celery"]["filename"] = "./logs/concordia-celery.log"
LOGGING["loggers"]["django"]["level"] = "INFO"
LOGGING["loggers"]["celery"]["level"] = "INFO"

# Pass the following environment into the stack when creating an AWS service:
# SENTRY_PUBLIC_DSN=http://f69265b381a44ceb89e9bd467f86fbdd@devops-sentry-public-lb-718357739.us-east-1.elb.amazonaws.com/3
# CELERY_BROKER_URL=pyamqp://guest@rabbit:5672
# AWS_DEFAULT_REGION=us-east-1
# AWS=1
# ENV_NAME=dev (or test, or stage, or prod)
# S3_BUCKET_NAME
# ELASTICSEARCH_ENDPOINT

if os.getenv("AWS"):
    ENV_NAME = os.getenv("ENV_NAME")

    django_secret_json = get_secret("crowd/%s/Django/SecretKey" % ENV_NAME)
    django_secret = json.loads(django_secret_json)
    DJANGO_SECRET_KEY = django_secret["DjangoSecretKey"]

    postgres_secret_json = get_secret("crowd/%s/DB/MasterUserPassword" % ENV_NAME)
    postgres_secret = json.loads(postgres_secret_json)

    DATABASES["default"].update(
        {"PASSWORD": postgres_secret["password"], "HOST": postgres_secret["host"]}
    )

    sentry_secret_json = get_secret("crowd/SentryDSN")
    sentry_secret = json.loads(sentry_secret_json)
    SENTRY_DSN = sentry_secret["SentryDSN"]
    RAVEN_CONFIG = {"dsn": SENTRY_DSN, "environment": CONCORDIA_ENVIRONMENT}

    smtp_secret_json = get_secret("concordia/SMTP")
    smtp_secret = json.loads(smtp_secret_json)
    EMAIL_HOST = smtp_secret["Hostname"]
    EMAIL_HOST_USER = smtp_secret["Username"]
    EMAIL_HOST_PASSWORD = smtp_secret["Password"]

else:
    DJANGO_SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "changeme")
    EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")


EMAIL_USE_TLS = True
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_PORT = 587
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "crowd@loc.gov")
DEFAULT_TO_EMAIL = DEFAULT_FROM_EMAIL

CSRF_COOKIE_SECURE = True

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "pyamqp://guest@rabbit:5672")
CELERY_RESULT_BACKEND = "rpc://"

S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
AWS_STORAGE_BUCKET_NAME = S3_BUCKET_NAME
AWS_DEFAULT_ACL = None  # Don't set an ACL on the files, inherit the bucket ACLs

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

IMPORTER = {
    # /concordia_images is a docker volume shared by importer and concordia
    "IMAGES_FOLDER": "/concordia_images/",
    "S3_BUCKET_NAME": S3_BUCKET_NAME,
}

MEDIA_URL = "https://%s.s3.amazonaws.com/" % S3_BUCKET_NAME

AWS_S3 = {
    "AWS_ACCESS_KEY_ID": AWS_ACCESS_KEY_ID,
    "AWS_SECRET_ACCESS_KEY": AWS_SECRET_ACCESS_KEY,
    "S3_COLLECTION_BUCKET": S3_BUCKET_NAME,
    "REGION": os.getenv("AWS_REGION"),
}

ELASTICSEARCH_DSL_AUTOSYNC = False

INSTALLED_APPS += ["django_elasticsearch_dsl"]

ELASTICSEARCH_DSL_SIGNAL_PROCESSOR = (
    "django_elasticsearch_dsl.signals.RealTimeSignalProcessor"
)
ELASTICSEARCH_DSL = {
    "default": {"hosts": os.getenv("ELASTICSEARCH_ENDPOINT", "elk:9200")}
}


# HMAC activation flow provide the two-step registration process,
# the user signs up and then completes activation via email instructions.

REGISTRATION_SALT = "django_registration"  # doesn't need to be secret

ACCOUNT_ACTIVATION_DAYS = 1  # required for HMAC registration two-step-flow
