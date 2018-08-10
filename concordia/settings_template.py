# TODO: use correct copyright header
import os
import sys

from dotenv import load_dotenv

from machina import MACHINA_MAIN_STATIC_DIR, MACHINA_MAIN_TEMPLATE_DIR
from machina import get_apps as get_machina_apps

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(PROJECT_DIR)

# Build path for and load .env file.
dotenv_path = os.path.join(BASE_DIR, '.env')
load_dotenv(dotenv_path)

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-secret-key"

# Optional SMTP authentication information for EMAIL_HOST.
EMAIL_HOST_USER = ""
EMAIL_HOST_PASSWORD = ""
EMAIL_USE_TLS = False
DEFAULT_FROM_EMAIL = "noreply@loc.gov"

ALLOWED_HOSTS = ["*"]

DEBUG = False
CSRF_COOKIE_SECURE = False

sys.path.append(PROJECT_DIR)
AUTH_PASSWORD_VALIDATORS = []
EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
# EMAIL_FILE_PATH = os.path.join(BASE_DIR, 'emails')
EMAIL_HOST = "localhost"
EMAIL_PORT = 25
LANGUAGE_CODE = "en-us"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
ROOT_URLCONF = "concordia.urls"
STATIC_ROOT = "static"
STATIC_URL = "/static/"
STATICFILES_DIRS = [
    os.path.join(PROJECT_DIR, "static"),
    os.path.join("/".join(PROJECT_DIR.split("/")[:-1]), "concordia/static"),
]
STATICFILES_DIRS = [os.path.join(PROJECT_DIR, "static"), MACHINA_MAIN_STATIC_DIR]
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
        "HOST": "db",
        "PORT": "5432",
    }
}


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
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
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Machina
    "machina.apps.forum_permission.middleware.ForumPermissionMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(PROJECT_DIR, "templates"), MACHINA_MAIN_TEMPLATE_DIR],
        #    'APP_DIRS': True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.media",
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
  "interval_max": 0.5
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
            "filename": "{}/logs/concordia.log".format(BASE_DIR),
            "when": "H",
            "interval": 3,
            "backupCount": 16,
        },
        "celery": {
            "level": "DEBUG",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "{}/logs/celery.log".format(BASE_DIR),
            "formatter": "long",
            "maxBytes": 1024 * 1024 * 100,  # 100 mb
        },
    },
    "loggers": {
        "django": {"handlers": ["file", "stream"], "level": "DEBUG", "propagate": True},
        "celery": {"handlers": ["celery", "stream"], "level": "DEBUG"},
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
    )
}

CONCORDIA = {"netloc": "http://0.0.0.0:80"}
MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")


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

AUTHENTICATION_BACKENDS = ['concordia.email_username_backend.EmailOrUsernameModelBackend']

REGISTRATION_URLS = "registration.backends.simple.urls"

CAPTCHA_CHALLENGE_FUNCT = 'captcha.helpers.random_char_challenge'
CAPTCHA_FIELD_TEMPLATE = 'captcha/field.html'
CAPTCHA_TEXT_FIELD_TEMPLATE = 'captcha/text_field.html'

AWS_S3 = {
    "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID"),
    "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY"),
    "S3_COLLECTION_BUCKET": "chc-collections"
}
