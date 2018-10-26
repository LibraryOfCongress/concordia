# TODO: use correct copyright header
import os

from django.contrib import messages

import raven

# Build paths inside the project like this: os.path.join(SITE_ROOT_DIR, ...)
CONCORDIA_APP_DIR = os.path.abspath(os.path.dirname(__file__))
SITE_ROOT_DIR = os.path.dirname(CONCORDIA_APP_DIR)

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
STATICFILES_DIRS = [os.path.join(CONCORDIA_APP_DIR, "static")]
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
        "PASSWORD": os.getenv("POSTGRESQL_PW"),
        "HOST": os.getenv("POSTGRESQL_HOST", "localhost"),
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
    "django.contrib.sites",
    "django.contrib.staticfiles",
    "raven.contrib.django.raven_compat",
    "maintenance_mode",
    "bootstrap4",
    "bittersweet",
    "concordia.apps.ConcordiaAppConfig",
    "exporter",
    "importer",
    "captcha",
    "django_prometheus_metrics",
    "robots",
]

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
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            os.path.join(SITE_ROOT_DIR, "templates"),
            os.path.join(CONCORDIA_APP_DIR, "templates"),
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
            ],
            "loaders": [
                "django.template.loaders.filesystem.Loader",
                "django.template.loaders.app_directories.Loader",
            ],
        },
    }
]

MEMCACHED_ADDRESS = os.getenv("MEMCACHED_ADDRESS", "")
MEMCACHED_PORT = os.getenv("MEMCACHED_PORT", "")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.memcached.MemcachedCache",
        "LOCATION": "{}:{}".format(MEMCACHED_ADDRESS, MEMCACHED_PORT),
    }
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

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(SITE_ROOT_DIR, "media")

LOGIN_URL = "login"

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

CAPTCHA_CHALLENGE_FUNCT = "captcha.helpers.random_char_challenge"
#: Anonymous sessions require captcha validation every day by default:
ANONYMOUS_CAPTCHA_VALIDATION_INTERVAL = 86400

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
WHITENOISE_ROOT = STATIC_ROOT

PASSWORD_RESET_TIMEOUT_DAYS = 1
ACCOUNT_ACTIVATION_DAYS = 1
REGISTRATION_OPEN = True  # set to false to temporarily disable registrations

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

MESSAGE_TAGS = {messages.ERROR: "danger"}

SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
SENTRY_PUBLIC_DSN = os.environ.get("SENTRY_PUBLIC_DSN", "")

RAVEN_CONFIG = {
    "dsn": SENTRY_DSN,
    "environment": CONCORDIA_ENVIRONMENT,
    "release": raven.fetch_git_sha(SITE_ROOT_DIR),
}

# When the MAINTENANCE_MODE setting is true, this template will be used to
# generate a 503 response:
MAINTENANCE_MODE_TEMPLATE = "maintenance-mode.html"

# Names of special django.auth Groups
COMMUNITY_MANAGER_GROUP_NAME = "Community Managers"
NEWSLETTER_GROUP_NAME = "Newsletter"

# Django sites framework setting
SITE_ID = 1
ROBOTS_USE_SITEMAP = False
ROBOTS_USE_HOST = False

# django-bootstrap4 customization:
BOOTSTRAP4 = {"required_css_class": "form-group-required"}

# Transcription-related settings

#: Number of seconds an asset reservation is valid for
TRANSCRIPTION_RESERVATION_SECONDS = 5 * 60

#: Web cache policy settings
DEFAULT_PAGE_TTL = 5 * 60
