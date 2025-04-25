import os

from .settings_template import *  # NOQA ignore=F405
from .settings_template import INSTALLED_APPS, LOGGING, MIDDLEWARE

LOGGING["handlers"]["stream"]["level"] = "DEBUG"
LOGGING["handlers"]["file"]["level"] = "DEBUG"
LOGGING["handlers"]["celery"]["level"] = "DEBUG"
LOGGING["loggers"] = {
    "django": {"handlers": ["file", "stream"], "level": "DEBUG"},
    "celery": {"handlers": ["celery", "stream"], "level": "DEBUG"},
    "concordia": {"handlers": ["file", "stream"], "level": "DEBUG"},
    "django.utils.autoreload": {"level": "INFO"},
    "django.template": {"level": "INFO"},
}

DEBUG = True

ALLOWED_HOSTS = ["127.0.0.1", "0.0.0.0", "*"]  # nosec

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
EMAIL_FILE_PATH = (
    "/tmp/concordia-messages"  # nosec — change this to a proper location for deployment
)
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "")
DEFAULT_TO_EMAIL = DEFAULT_FROM_EMAIL

INSTALLED_APPS += ["django_opensearch_dsl"]

# Globally disable auto-syncing. Automatically update the index when a model is
# created / saved / deleted.
OPENSEARCH_DSL_AUTOSYNC = False

OPENSEARCH_DSL = {
    "default": {"hosts": "localhost:9200"},
    "secure": {
        "hosts": [{"scheme": "https", "host": "192.30.255.112", "port": 9201}],
        "http_auth": ("admin", "admin"),
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
