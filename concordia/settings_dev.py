import os

from .settings_template import *  # NOQA ignore=F405
from .settings_template import INSTALLED_APPS, LOGGING, MIDDLEWARE

LOGGING["handlers"]["stream"]["level"] = "DEBUG"
LOGGING["handlers"]["file"]["level"] = "DEBUG"
LOGGING["handlers"]["celery"]["level"] = "DEBUG"
LOGGING["handlers"]["structlog"]["level"] = "DEBUG"
LOGGING["handlers"]["django_structlog"]["level"] = "DEBUG"
LOGGING["loggers"] = {
    "django": {"handlers": ["file", "stream"], "level": "DEBUG"},
    "celery": {"handlers": ["celery", "stream"], "level": "DEBUG"},
    "concordia": {"handlers": ["file", "stream"], "level": "DEBUG"},
    "django.utils.autoreload": {"level": "INFO"},
    "django.template": {"level": "INFO"},
    "aws_xray_sdk": {
        "handlers": ["file", "stream"],
        "level": "DEBUG",
        "propagate": True,
    },
    "structlog": {
        "handlers": ["structlog_file", "structlog_console"],
        "level": "INFO",
    },
    "django_structlog": {
        "handlers": ["structlog_file", "structlog_console"],
        "level": "INFO",
    },
}

DEBUG = True

ALLOWED_HOSTS = ["127.0.0.1", "0.0.0.0", "*"]  # nosec

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
EMAIL_FILE_PATH = (
    "/tmp/concordia-messages"  # nosec — change this to a proper location for deployment
)
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "")
DEFAULT_TO_EMAIL = DEFAULT_FROM_EMAIL
CONCORDIA_DEVS = [
    "rsar@loc.gov",
]

INSTALLED_APPS += ["django_opensearch_dsl"]

# Globally disable auto-syncing. Automatically update the index when a model is
# created / saved / deleted.
OPENSEARCH_DSL_AUTOSYNC = False

OPENSEARCH_DSL = {
    "default": {"hosts": "localhost:9200"},
    "secure": {
        "hosts": [{"scheme": "https", "host": "192.30.255.112", "port": 9201}],
        "http_auth": ("admin", os.environ.get("OPENSEARCH_INITIAL_ADMIN_PASSWORD", "")),
        "timeout": 120,
    },
}

REGISTRATION_SALT = "django_registration"  # doesn't need to be secret

INSTALLED_APPS += ["debug_toolbar"]
MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]
INTERNAL_IPS = ("127.0.0.1",)

INSTALLED_APPS += ("django_extensions",)
SHELL_PLUS_PRE_IMPORTS = [
    ("concordia.utils", "get_anonymous_user"),
    ("concordia.models", "TranscriptionStatus"),
]

# X-Ray configuration for local development
if os.environ.get("AWS_XRAY_SDK_ENABLED", "false").lower() == "true":
    import logging

    logger = logging.getLogger(__name__)

    logger.info("ECS X-Ray auto-instrumentation starting")

    # Add X-Ray to INSTALLED_APPS
    INSTALLED_APPS = INSTALLED_APPS + ["aws_xray_sdk.ext.django"]

    # Add middleware - MUST be first in the list
    MIDDLEWARE = ["aws_xray_sdk.ext.django.middleware.XRayMiddleware"] + MIDDLEWARE

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
