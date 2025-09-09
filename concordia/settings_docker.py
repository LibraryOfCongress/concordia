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
        "http_auth": ("admin", os.environ.get("OPENSEARCH_INITIAL_ADMIN_PASSWORD", "")),
        "timeout": 120,
    },
}

# X-Ray configuration for local development
if os.environ.get("AWS_XRAY_SDK_ENABLED", "false").lower() == "true":
    import logging

    logger = logging.getLogger(__name__)

    logger.info("ECS X-Ray auto-instrumentation starting")

    # Add X-Ray to INSTALLED_APPS
    INSTALLED_APPS = INSTALLED_APPS + ["aws_xray_sdk.ext.django"]

    # Add middleware - MUST be first in the list
    MIDDLEWARE = [
        "aws_xray_sdk.ext.django.middleware.XRayMiddleware"
    ] + MIDDLEWARE  # noqa F405

    logger.info("ECS X-Ray auto-instrumentation completed")
    logger.info("X-Ray middleware added at position 0: %s", MIDDLEWARE[0])
    logger.info("Current MIDDLEWARE[0]: %s", MIDDLEWARE[0])

    XRAY_RECORDER = {
        "AWS_XRAY_DAEMON_ADDRESS": os.environ.get(
            "AWS_XRAY_DAEMON_ADDRESS", "127.0.0.1:2000"
        ),
        "AUTO_INSTRUMENT": True,
        "AWS_XRAY_CONTEXT_MISSING": os.environ.get(
            "AWS_XRAY_CONTEXT_MISSING", "LOG_ERROR"
        ),
        "PLUGINS": (),
        "AWS_XRAY_TRACING_NAME": os.environ.get(
            "AWS_XRAY_TRACING_NAME",
            os.environ.get("CONCORDIA_ENVIRONMENT", "development"),
        ),
        "PATCH_MODULES": ["boto3", "botocore", "requests", "httplib", "psycopg2"],
        "SAMPLING": False,
        "IGNORE_MODULE_PATTERNS": [
            r"^debug_toolbar\.",
            r"^django\.contrib\.admin\.views\.decorators\.cache",
            r"^django\.contrib\.admin\.options",
            r"^django\.contrib\.admin\.options\.ModelAdmin",
            r"^django\.contrib\.admin\.options\.InlineModelAdmin",
            r"^django\.contrib\.admin\.options\.BaseModelAdmin",
            r"^django\.contrib\.admin\.options\.ModelAdminMixin",
            r"^django\.contrib\.admin\.options\.InlineModelAdminMixin",
            r"^django\.contrib\.admin\.options\.ModelAdminBase",
            r"^django\.contrib\.admin\.options\.InlineModelAdminBase",
            r"^django\.contrib\.admin\.options\.ModelAdminMixinBase",
            r"^django\.contrib\.admin\.options\.InlineModelAdminMixinBase",
            r"^django\.contrib\.admin\.options\.ModelAdminDecorator",
            r"^django\.contrib\.admin\.options\.InlineModelAdminDecorator",
            r"^django\.contrib\.admin\.options\.ModelAdminDecoratorMixin",
            r"^django\.contrib\.admin\.options\.InlineModelAdminDecoratorMixin",
            r"^django\.contrib\.admin\.options\.ModelAdminDecoratorBase",
            r"^django\.contrib\.admin\.options\.InlineModelAdminDecoratorBase",
        ],
    }


# HMAC activation flow provide the two-step registration process,
# the user signs up and then completes activation via email instructions.

# This is *not* a secret for the HMAC activation workflow — see:
# https://django-registration.readthedocs.io/en/2.0.4/hmac.html#security-considerations
REGISTRATION_SALT = "django_registration"

RATELIMIT_BLOCK = os.getenv("RATELIMIT_BLOCK", "").lower() not in ("false", "0")
