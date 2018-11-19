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

if os.getenv("AWS"):
    ENV_NAME = os.getenv("ENV_NAME")

    django_secret_json = get_secret("crowd/%s/Django/SecretKey" % ENV_NAME)
    django_secret = json.loads(django_secret_json)
    DJANGO_SECRET_KEY = django_secret["DjangoSecretKey"]

    postgres_secret_json = get_secret("crowd/%s/DB/MasterUserPassword" % ENV_NAME)
    postgres_secret = json.loads(postgres_secret_json)

    DATABASES["default"].update({"PASSWORD": postgres_secret["password"]})

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

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

EMAIL_USE_TLS = True
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_PORT = 587
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "crowd@loc.gov")
DEFAULT_TO_EMAIL = DEFAULT_FROM_EMAIL

CSRF_COOKIE_SECURE = True

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "pyamqp://guest@rabbit:5672")
CELERY_RESULT_BACKEND = "rpc://"

S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
EXPORT_S3_BUCKET_NAME = os.getenv("EXPORT_S3_BUCKET_NAME")

DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
AWS_STORAGE_BUCKET_NAME = S3_BUCKET_NAME
AWS_DEFAULT_ACL = None  # Don't set an ACL on the files, inherit the bucket ACLs

if CONCORDIA_ENVIRONMENT == "production":
    MEDIA_URL = "https://crowd-media.loc.gov/"
else:
    MEDIA_URL = "https://%s.s3.amazonaws.com/" % S3_BUCKET_NAME

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

SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"

if os.getenv("RATELIMIT_BLOCK"):
    RATELIMIT_BLOCK = os.getenv("RATELIMIT_BLOCK")
    if RATELIMIT_BLOCK.lower() == "false" or RATELIMIT_BLOCK == 0:
        RATELIMIT_BLOCK = False
    else:
        RATELIMIT_BLOCK = True
else:
    RATELIMIT_BLOCK = True
