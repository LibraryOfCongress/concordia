import json
import os

from .secrets import get_secret
from .settings_template import *  # NOQA ignore=F405
from .settings_template import (
    CONCORDIA_ENVIRONMENT,
    DATABASES,
    INSTALLED_APPS,
    MIDDLEWARE,
    STORAGES,
)

if os.getenv("AWS"):
    ENV_NAME = os.getenv("ENV_NAME")

    django_secret_json = get_secret("crowd/%s/Django/SecretKey" % ENV_NAME)
    django_secret = json.loads(django_secret_json)
    SECRET_KEY = django_secret["DjangoSecretKey"]

    postgres_secret_json = get_secret("crowd/%s/DB/MasterUserPassword" % ENV_NAME)
    postgres_secret = json.loads(postgres_secret_json)

    DATABASES["default"].update({"PASSWORD": postgres_secret["password"]})

    cf_turnstile_secret_json = get_secret("crowd/%s/Turnstile" % ENV_NAME)
    cf_turnstile_secret = json.loads(cf_turnstile_secret_json)
    TURNSTILE_SITEKEY = cf_turnstile_secret["TurnstileSiteKey"]
    TURNSTILE_SECRET = cf_turnstile_secret["TurnstileSecret"]

    smtp_secret_json = get_secret("concordia/SMTP")
    smtp_secret = json.loads(smtp_secret_json)
    EMAIL_HOST = smtp_secret["Hostname"]
    EMAIL_HOST_USER = smtp_secret["Username"]
    EMAIL_HOST_PASSWORD = smtp_secret["Password"]

else:
    EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

EMAIL_USE_TLS = True
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_PORT = 587
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "crowd@loc.gov")
DEFAULT_TO_EMAIL = DEFAULT_FROM_EMAIL
CONCORDIA_DEVS = [
    "jkue@loc.gov",
    "jstegmaier@loc.gov",
    "rsar@loc.gov",
]

CSRF_COOKIE_SECURE = True

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL

S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
EXPORT_S3_BUCKET_NAME = os.getenv("EXPORT_S3_BUCKET_NAME")

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
            "bucket_name": EXPORT_S3_BUCKET_NAME,
        },
    },
}
AWS_STORAGE_BUCKET_NAME = S3_BUCKET_NAME
AWS_DEFAULT_ACL = None  # Don't set an ACL on the files, inherit the bucket ACLs

if CONCORDIA_ENVIRONMENT == "production":
    MEDIA_URL = "https://crowd-media.loc.gov/"
else:
    MEDIA_URL = "https://%s.s3.amazonaws.com/" % S3_BUCKET_NAME

INSTALLED_APPS += ["django_opensearch_dsl"]

# Globally disable auto-syncing
OPENSEARCH_DSL_AUTOSYNC = os.getenv("OPENSEARCH_DSL_AUTOSYNC", False)

OPENSEARCH_DSL = {
    "default": {"hosts": os.getenv("OPENSEARCH_ENDPOINT", "opensearch-node:9200")}
}

# HMAC activation flow provide the two-step registration process,
# the user signs up and then completes activation via email instructions.

REGISTRATION_SALT = "django_registration"  # doesn't need to be secret

RATELIMIT_BLOCK = os.getenv("RATELIMIT_BLOCK", "").lower() not in ("false", "0")

if os.getenv("USE_PERSISTENT_DATABASE_CONNECTIONS"):
    DATABASES["default"].update({"CONN_MAX_AGE": 15 * 60})

# ECS-specific X-Ray auto-instrumentation (minimal Django config)
if os.environ.get("AWS_XRAY_SDK_ENABLED", "false").lower() == "true":
    import logging

    logger = logging.getLogger(__name__)

    logger.info("ECS X-Ray auto-instrumentation starting")

    # Add X-Ray to INSTALLED_APPS
    INSTALLED_APPS = INSTALLED_APPS + ["aws_xray_sdk.ext.django"]

    # Add middleware
    MIDDLEWARE = [
        "aws_xray_sdk.ext.django.middleware.XRayMiddleware"
    ] + MIDDLEWARE  # noqa F405

    logger.info("ECS X-Ray auto-instrumentation completed")
    logger.info("X-Ray middleware added at position 0: %s", MIDDLEWARE[0])
    logger.info("aws_xray_sdk.ext.django added to INSTALLED_APPS")
    logger.info("All X-Ray configuration handled via environment variables")
