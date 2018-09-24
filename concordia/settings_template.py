# TODO: use correct copyright header
import os

from django.contrib import messages
from dotenv import load_dotenv
from machina import MACHINA_MAIN_STATIC_DIR, MACHINA_MAIN_TEMPLATE_DIR
from machina import get_apps as get_machina_apps

# Build paths inside the project like this: os.path.join(SITE_ROOT_DIR, ...)
CONCORDIA_APP_DIR = os.path.abspath(os.path.dirname(__file__))
SITE_ROOT_DIR = os.path.dirname(CONCORDIA_APP_DIR)

# Build path for and load .env file.
dotenv_path = os.path.join(SITE_ROOT_DIR, ".env")
load_dotenv(dotenv_path)

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-secret-key"

CONCORDIA_ENVIRONMENT = os.environ.get("CONCORDIA_ENVIRONMENT", "development")

# Optional SMTP authentication information for EMAIL_HOST.
EMAIL_HOST_USER = ""
EMAIL_HOST_PASSWORD = ""
EMAIL_USE_TLS = False
DEFAULT_FROM_EMAIL = "crowd@loc.gov"

ALLOWED_HOSTS = ["*"]

DEBUG = False
CSRF_COOKIE_SECURE = False

AUTH_PASSWORD_VALIDATORS = []
EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
# EMAIL_FILE_PATH = os.path.join(SITE_ROOT_DIR, 'emails')
EMAIL_HOST = "localhost"
EMAIL_PORT = 25
LANGUAGE_CODE = "en-us"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
ROOT_URLCONF = "concordia.urls"
STATIC_ROOT = "static"
STATIC_URL = "/static/"
STATICFILES_DIRS = [
    os.path.join(CONCORDIA_APP_DIR, "static"),
    os.path.join("/".join(CONCORDIA_APP_DIR.split("/")[:-1]), "concordia/static"),
]
STATICFILES_DIRS = [os.path.join(CONCORDIA_APP_DIR, "static"), MACHINA_MAIN_STATIC_DIR]
TEMPLATE_DEBUG = False
TIME_ZONE = "UTC"
USE_I18N = True
USE_L10N = True
USE_TZ = True
WSGI_APPLICATION = "concordia.wsgi.application"

ADMIN_SITE = {"site_header": "Concordia Admin", "site_title": "Concordia"}

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "concordia",
        "USER": "concordia",
        "PASSWORD": "$(POSTGRESQL_PW)",
        "HOST": "$(POSTGRESQL_HOST)",
        "PORT": "5432",
        "CONN_MAX_AGE": 15 * 60,  # Keep database connections open for 15 minutes
    }
}


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.humanize",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "raven.contrib.django.raven_compat",
    "maintenance_mode",
    "rest_framework",
    "concordia",
    "exporter",
    "faq",
    "importer",
    "concordia.experiments.wireframes",
    "captcha",
    # Machina related apps:
    "mptt",
    "haystack",
    "widget_tweaks",
    "django_prometheus_metrics",
] + get_machina_apps()


if DEBUG:
    INSTALLED_APPS += ["django_extensions"]
    INSTALLED_APPS += ["kombu.transport"]


MIDDLEWARE = [
    "django_prometheus_metrics.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves static files efficiently:
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "maintenance_mode.middleware.MaintenanceModeMiddleware",
    # Machina
    "machina.apps.forum_permission.middleware.ForumPermissionMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            os.path.join(SITE_ROOT_DIR, "templates"),
            os.path.join(CONCORDIA_APP_DIR, "templates"),
            MACHINA_MAIN_TEMPLATE_DIR,
        ],
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.media",
                # Concordia
                "concordia.context_processors.system_configuration",
                "concordia.context_processors.site_navigation",
                # Machina
                "machina.core.context_processors.metadata",
            ],
            "loaders": [
                "django.template.loaders.filesystem.Loader",
                "django.template.loaders.app_directories.Loader",
            ],
        },
    }
]

CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "machina_attachments": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": "/tmp",
    },
}

HAYSTACK_CONNECTIONS = {
    "default": {
        "ENGINE": "haystack.backends.whoosh_backend.WhooshEngine",
        "PATH": os.path.join(os.path.dirname(__file__), "whoosh_index"),
    }
}

# Celery settings
CELERY_BROKER_URL = "pyamqp://guest@rabbit"
CELERY_RESULT_BACKEND = "rpc://"

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_IMPORTS = ("importer.tasks",)

CELERY_BROKER_HEARTBEAT = 0
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "confirm_publish": True,
    "max_retries": 3,
    "interval_start": 0,
    "interval_step": 0.2,
    "interval_max": 0.5,
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "long": {
            "format": "[{asctime} {levelname} {name}:{lineno}] {message}",
            "datefmt": "%Y-%m-%dT%H:%M:%S",
            "style": "{",
        },
        "short": {
            "format": "[{levelname} {name}] {message}",
            "datefmt": "%Y-%m-%dT%H:%M:%S",
            "style": "{",
        },
    },
    "handlers": {
        "stream": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "long",
        },
        "null": {"level": "DEBUG", "class": "logging.NullHandler"},
        "file": {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "level": "DEBUG",
            "formatter": "long",
            "filename": "{}/logs/concordia.log".format(SITE_ROOT_DIR),
            "when": "H",
            "interval": 3,
            "backupCount": 16,
        },
        "celery": {
            "level": "DEBUG",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "{}/logs/celery.log".format(SITE_ROOT_DIR),
            "formatter": "long",
            "maxBytes": 1024 * 1024 * 100,  # 100 mb
        },
        "sentry": {
            "level": "WARNING",
            "class": "raven.contrib.django.raven_compat.handlers.SentryHandler",
        },
    },
    "loggers": {
        "django": {"handlers": ["file", "stream"], "level": "DEBUG", "propagate": True},
        "celery": {"handlers": ["celery", "stream"], "level": "DEBUG"},
        "sentry.errors": {"level": "INFO", "handlers": ["stream"], "propagate": False},
    },
}


################################################################################
# Django-specific settings above
################################################################################

ACCOUNT_ACTIVATION_DAYS = 7

REST_FRAMEWORK = {
    "PAGE_SIZE": 10,
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.BasicAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
}

CONCORDIA = {"netloc": "http://0:80"}
MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(SITE_ROOT_DIR, "media")


LOGIN_URL = "/account/login/"

PASSWORD_VALIDATOR = (
    "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
)

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": PASSWORD_VALIDATOR},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "concordia.validators.complexity"},
]

AUTHENTICATION_BACKENDS = [
    "concordia.email_username_backend.EmailOrUsernameModelBackend"
]

REGISTRATION_URLS = "registration.backends.simple.urls"

CAPTCHA_CHALLENGE_FUNCT = "captcha.helpers.random_char_challenge"
CAPTCHA_FIELD_TEMPLATE = "captcha/field.html"
CAPTCHA_TEXT_FIELD_TEMPLATE = "captcha/text_field.html"

AWS_S3 = {
    "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID"),
    "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY"),
    "S3_COLLECTION_BUCKET": os.getenv("S3_BUCKET_NAME"),
    "REGION": os.getenv("AWS_REGION"),
}

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
WHITENOISE_ROOT = STATIC_ROOT

PASSWORD_RESET_TIMEOUT_DAYS = 1
ACCOUNT_ACTIVATION_DAYS = 1
REGISTRATION_OPEN = True  # set to false to temporarily disable registrations

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

MESSAGE_TAGS = {messages.ERROR: "danger"}

SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
SENTRY_PUBLIC_DSN = os.environ.get("SENTRY_PUBLIC_DSN", "")

if SENTRY_DSN:
    RAVEN_CONFIG = {"dsn": SENTRY_DSN, "environment": CONCORDIA_ENVIRONMENT}

# When the MAINTENANCE_MODE setting is true, this template will be used to
# generate a 503 response:
MAINTENANCE_MODE_TEMPLATE = "maintenance-mode.html"
