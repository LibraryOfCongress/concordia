import os

import sentry_sdk
import structlog
from django.contrib import messages
from django.core.management.utils import get_random_secret_key
from sentry_sdk.integrations.django import DjangoIntegration

from concordia.version import get_concordia_version

# New in 3.2, if no field in a model is defined with primary_key=True an implicit
# primary key is added. This can now be controlled by changing the value below
# 3.2 default value is BigAutoField. But migrations does not support M2M PK
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# Build paths inside the project like this: os.path.join(SITE_ROOT_DIR, ...)
CONCORDIA_APP_DIR = os.path.abspath(os.path.dirname(__file__))
SITE_ROOT_DIR = os.path.dirname(CONCORDIA_APP_DIR)

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", get_random_secret_key())

CONCORDIA_ENVIRONMENT = os.environ.get("CONCORDIA_ENVIRONMENT", "development")
DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760
# Optional SMTP authentication information for EMAIL_HOST.
EMAIL_HOST_USER = ""
EMAIL_HOST_PASSWORD = ""  # nosec
EMAIL_USE_TLS = False
DEFAULT_FROM_EMAIL = "crowd@loc.gov"

ALLOWED_HOSTS = ["*"]

DEBUG = False
CSRF_COOKIE_SECURE = False

AUTH_PASSWORD_VALIDATORS = []
EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
EMAIL_HOST = "localhost"
EMAIL_PORT = 25
LANGUAGE_CODE = "en-us"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
ROOT_URLCONF = "concordia.urls"
STATIC_ROOT = "static-files"
STATIC_URL = "/static/"

STATICFILES_FINDERS = [
    # We let the filesystem override the app directories so Gulp can pre-process
    # files if needed:
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
    # See https://github.com/kevin1024/django-npm
    "npm.finders.NpmFinder",
]

STATICFILES_DIRS = [
    os.path.join(SITE_ROOT_DIR, "static"),
]

NPM_FILE_PATTERNS = {
    "redom": ["dist/*"],
    "split.js": ["dist/*"],
    "urijs": ["src/*"],
    "openseadragon": ["build/*"],
    "openseadragon-filtering": ["openseadragon-filtering.js"],
    "codemirror": ["lib/*", "addon/*", "mode/*"],
    "prettier": ["*.js"],
    "remarkable": ["dist/*"],
    "jquery": ["dist/*"],
    "js-cookie": ["dist/*"],
    "@popperjs/core": ["dist/*"],
    "bootstrap": ["dist/*"],
    "screenfull": ["*"],
    "@duetds/date-picker/": ["dist/*"],
    "@fortawesome/fontawesome-free/": [
        "css/*",
        "js/*",
        "sprites/*",
        "svgs/*",
        "webfonts/*",
    ],
    "chart.js": ["auto/*", "dist/*"],
    "@kurkle/color": ["dist/*"],
    "chroma-js": ["dist/*"],
    "@sentry": ["*"],
    "@sentry-internal": ["*"],
}

TEMPLATE_DEBUG = False
TIME_ZONE = "America/New_York"
USE_I18N = True
USE_TZ = True
WSGI_APPLICATION = "concordia.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "concordia",
        "USER": "concordia",
        "PASSWORD": os.getenv("POSTGRESQL_PW"),
        "HOST": os.getenv("POSTGRESQL_HOST", "localhost"),
        "PORT": os.getenv("POSTGRESQL_PORT", "5432"),
        # Change this back to 15 minutes (15*60) once celery regression
        # is fixed  see https://github.com/celery/celery/issues/4878
        "CONN_MAX_AGE": 0,  # 15 minutes
    }
}

INSTALLED_APPS = [
    "concordia.apps.ConcordiaAdminConfig",  # Replaces 'django.contrib.admin'
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.humanize",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.sites",
    # Replaces "django.contrib.staticfiles",
    "concordia.apps.ConcordiaStaticFilesConfig",
    "django_structlog",
    "django_bootstrap5",
    "maintenance_mode",
    "concordia.apps.ConcordiaAppConfig",
    "exporter",
    "importer",
    "configuration",
    "prometheus_metrics.apps.PrometheusMetricsConfig",
    "robots",
    "django_celery_beat",
    "flags",
    "channels",
    "django_admin_multiple_choice_list_filter",
    "tinymce",
]

MIDDLEWARE = [
    "prometheus_metrics.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves static files efficiently:
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_structlog.middlewares.RequestMiddleware",
    "django_ratelimit.middleware.RatelimitMiddleware",
    "concordia.middleware.MaintenanceModeMiddleware",
]

RATELIMIT_VIEW = "concordia.views.rate_limit.ratelimit_view"
RATELIMIT_BLOCK = False

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
                "maintenance_mode.context_processors.maintenance_mode",
                # Concordia
                "concordia.context_processors.system_configuration",
                "concordia.context_processors.site_navigation",
                "concordia.context_processors.maintenance_mode_frontend_available",
                "concordia.context_processors.request_id_context",
                "concordia.turnstile.context_processors.turnstile_default_settings",
            ],
            "libraries": {
                "staticfiles": "django.templatetags.static",
            },
            "loaders": [
                "django.template.loaders.filesystem.Loader",
                "django.template.loaders.app_directories.Loader",
            ],
            "builtins": [
                "configuration.templatetags.configuration_tags",
                "concordia.templatetags.reject_filter",
            ],
        },
    }
]

HAYSTACK_CONNECTIONS = {
    "default": {
        "ENGINE": "haystack.backends.whoosh_backend.WhooshEngine",
        "PATH": os.path.join(os.path.dirname(__file__), "whoosh_index"),
    }
}

REDIS_ADDRESS = os.environ.get("REDIS_ADDRESS", "localhost")
REDIS_PORT = os.environ.get("REDIS_PORT", "")
if REDIS_PORT.isdigit():
    REDIS_PORT = int(REDIS_PORT)
else:
    REDIS_PORT = 6379

if REDIS_ADDRESS and REDIS_PORT:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": f"redis://{REDIS_ADDRESS}:{REDIS_PORT}/1",
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
            },
        },
        "view_cache": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": f"redis://{REDIS_ADDRESS}:{REDIS_PORT}/2",
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
            },
        },
        "configuration_cache": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": f"redis://{REDIS_ADDRESS}:{REDIS_PORT}/3",
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
            },
        },
        "visualization_cache": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": f"redis://{REDIS_ADDRESS}:{REDIS_PORT}/4",
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
            },
        },
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        },
        "view_cache": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
        "configuration_cache": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache"
        },
        "visualization_cache": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache"
        },
    }

SESSION_ENGINE = "django.contrib.sessions.backends.db"

CELERY_BROKER_URL = f"redis://{REDIS_ADDRESS}:{REDIS_PORT}/0"
CELERY_RESULT_BACKEND = f"redis://{REDIS_ADDRESS}:{REDIS_PORT}/0"

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_IMPORTS = ("importer.tasks",)

CELERY_BROKER_HEARTBEAT = 0
CELERY_BROKER_CONNECTION_RETRY = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
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
        "structlog_json": {
            "()": structlog.stdlib.ProcessorFormatter,
            "processor": structlog.processors.JSONRenderer(),
        },
        "structlog_console": {
            "()": structlog.stdlib.ProcessorFormatter,
            "processor": structlog.dev.ConsoleRenderer(),
        },
    },
    "handlers": {
        "stream": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "long",
        },
        "null": {"level": "INFO", "class": "logging.NullHandler"},
        "file": {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "level": "INFO",
            "formatter": "long",
            "filename": f"{SITE_ROOT_DIR}/logs/concordia.log",
            "when": "H",
            "interval": 3,
            "backupCount": 16,
        },
        "celery": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": f"{SITE_ROOT_DIR}/logs/celery.log",
            "formatter": "long",
            "maxBytes": 1024 * 1024 * 100,  # 100 mb
        },
        "structlog_file": {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "level": "DEBUG",
            "formatter": "structlog_json",
            "filename": f"{SITE_ROOT_DIR}/logs/concordia-json.log",
            "when": "H",
            "interval": 3,
            "backupCount": 16,
        },
        "structlog_console": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "structlog_console",
        },
    },
    "loggers": {
        "django": {"handlers": ["file"], "level": "INFO"},
        "celery": {"handlers": ["celery"], "level": "INFO"},
        "concordia": {"handlers": ["file"], "level": "INFO"},
        "aws_xray_sdk": {"handlers": ["file"], "level": "INFO", "propagate": True},
        "structlog": {
            "handlers": ["structlog_file"],
            "level": "DEBUG",
            "propagate": True,
        },
        "django_structlog": {
            "handlers": ["structlog_file"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)


################################################################################
# Django-specific settings above
################################################################################

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(SITE_ROOT_DIR, "media")

LOGIN_URL = "login"

PASSWORD_VALIDATOR = (
    "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"  # nosec
)

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": PASSWORD_VALIDATOR},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "concordia.validators.DjangoPasswordsValidator"},
]

# See https://github.com/dstufft/django-passwords#settings
PASSWORD_COMPLEXITY = {
    "UPPER": 1,
    "LOWER": 1,
    "LETTERS": 1,
    "DIGITS": 1,
    "SPECIAL": 1,
    "WORDS": 1,
}

AUTHENTICATION_BACKENDS = [
    "concordia.authentication_backends.EmailOrUsernameModelBackend"
]

# Turnstile settings
TURNSTILE_JS_API_URL = os.environ.get(
    "TURNSTILE_JS_API_URL", "https://challenges.cloudflare.com/turnstile/v0/api.js"
)
TURNSTILE_VERIFY_URL = os.environ.get(
    "TURNSTILE_VERIFY_URL", "https://challenges.cloudflare.com/turnstile/v0/siteverify"
)
TURNSTILE_SITEKEY = os.environ.get("TURNSTILE_SITEKEY", "")
TURNSTILE_SECRET = os.environ.get("TURNSTILE_SECRET", "")
TURNSTILE_TIMEOUT = os.environ.get("TURNSTILE_TIMEOUT", 5)
TURNSTILE_DEFAULT_CONFIG = os.environ.get(
    "TURNSTILE_DEFAULT_CONFIG", {"appearance": "interaction-only"}
)
TURNSTILE_PROXIES = os.environ.get("TURNSTILE_PROXIES", {})
ANONYMOUS_USER_VALIDATION_INTERVAL = 86400

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
    "assets": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "visualizations": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
}
WHITENOISE_ROOT = os.path.join(SITE_ROOT_DIR, "static")

PASSWORD_RESET_TIMEOUT = 604800
ACCOUNT_ACTIVATION_DAYS = 7
REGISTRATION_OPEN = True  # set to false to temporarily disable registrations

REQUIRE_EMAIL_RECONFIRMATION = True
EMAIL_RECONFIRMATION_KEY = "EMAIL_CONFIRMATION_{id}"
EMAIL_RECONFIRMATION_DAYS = 7
EMAIL_RECONFIRMATION_TIMEOUT = 60 * 60 * 24 * EMAIL_RECONFIRMATION_DAYS

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

MESSAGE_TAGS = {messages.ERROR: "danger"}

SENTRY_BACKEND_DSN = os.environ.get("SENTRY_BACKEND_DSN", "")
SENTRY_FRONTEND_DSN = os.environ.get("SENTRY_FRONTEND_DSN", "")

APPLICATION_VERSION = get_concordia_version()

sentry_sdk.init(
    dsn=SENTRY_BACKEND_DSN,
    environment=CONCORDIA_ENVIRONMENT,
    release=APPLICATION_VERSION,
    integrations=[DjangoIntegration()],
)

# Names of special django.auth Groups
COMMUNITY_MANAGER_GROUP_NAME = "Community Managers"
NEWSLETTER_GROUP_NAME = "Newsletter"

# Django sites framework setting
SITE_ID = 1
ROBOTS_USE_SITEMAP = False
ROBOTS_USE_HOST = False

# django-bootstrap4 customization:
BOOTSTRAP4 = {"required_css_class": "form-group-required", "set_placeholder": False}

# Transcription-related settings

#: Number of seconds an asset reservation is valid for
TRANSCRIPTION_RESERVATION_SECONDS = 15 * 60

#: Number of hours until an asset reservation is tombstoned
TRANSCRIPTION_RESERVATION_TOMBSTONE_HOURS = 24

#: Number of hours until a tombstoned reservation is deleted
TRANSCRIPTION_RESERVATION_TOMBSTONE_LENGTH_HOURS = 24

#: Web cache policy settings
DEFAULT_PAGE_TTL = 5 * 60

# Feature flags
FLAGS = {
    "ADVERTISE_ACTIVITY_UI": [],
    "CAROUSEL_CMS": [],
    "SEND_WELCOME_EMAIL": [],
    "SHOW_BANNER": [],
    "DISPLAY_ITEM_DESCRIPTION": [],
    "IMPORT_IMAGE_CHECKSUM": [],
}

ASGI_APPLICATION = "concordia.routing.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [(REDIS_ADDRESS, REDIS_PORT)],
            "capacity": 1500,
            "expiry": 10,
        },
    }
}

SECURE_REFERRER_POLICY = "origin"
TINYMCE_COMPRESSOR = False
TINYMCE_DEFAULT_CONFIG = {
    "selector": "textarea.tinymce",
    "referrer_policy": "origin",
    "skin": "oxide-dark",
    "content_css": "dark",
    "plugins": "link lists searchreplace wordcount",
    "browser_spellcheck": "true",
    "newline_behavior": "linebreak",
    "toolbar1": "bold italic | numlist bullist | link | searchreplace wordcount",
    "width": 624,
}
TINYMCE_JS_URL = "https://cdn.tiny.cloud/1/rf486i5f1ww9m8191oolczn7f0ry61mzdtfwbu7maiiiv2kv/tinymce/6/tinymce.min.js"

LANGUAGE_CODES = {
    "eng": "English (default)",
    "afr": "Afrikaans",
    "sqi": "Albanian",
    "amh": "Amharic",
    "ara": "Arabic",
    "asm": "Assamese",
    "aze": "Azerbaijani",
    "aze_cyrl": "Azerbaijani - Cyrillic",
    "eus": "Basque",
    "bel": "Belarusian",
    "ben": "Bengali",
    "bos": "Bosnian",
    "bul": "Bulgarian",
    "mya": "Burmese",
    "cat": "Catalan; Valencian",
    "ceb": "Cebuano",
    "khm": "Central Khmer",
    "chr": "Cherokee",
    "chi_sim": "Chinese - Simplified",
    "chi_tra": "Chinese - Traditional",
    "hrv": "Croatian",
    "ces": "Czech",
    "dan": "Danish",
    "nld": "Dutch; Flemish",
    "dzo": "Dzongkha",
    "enm": "English, Middle (1100-1500)",
    "epo": "Esperanto",
    "est": "Estonian",
    "kat": "Georgian",
    "kat_old": "Georgian - Old",
    "deu": "German",
    "ell": "Greek, Modern (1453-)",
    "fin": "Finnish",
    "fra": "French",
    "frm": "French, Middle (ca. 1400-1600)",
    "glg": "Galician",
    "frk": "German Fraktur",
    "grc": "Greek, Ancient (-1453)",
    "guj": "Gujarati",
    "hat": "Haitian; Haitian Creole",
    "heb": "Hebrew",
    "hin": "Hindi",
    "hun": "Hungarian",
    "isl": "Icelandic",
    "ind": "Indonesian",
    "iku": "Inuktitut",
    "gle": "Irish",
    "ita": "Italian",
    "ita_old": "Italian - Old",
    "jpn": "Japanese",
    "jav": "Javanese",
    "kan": "Kannada",
    "kaz": "Kazakh",
    "kir": "Kirghiz; Kyrgyz",
    "kor": "Korean",
    "kur": "Kurdish",
    "lao": "Lao",
    "lat": "Latin",
    "lav": "Latvian",
    "lit": "Lithuanian",
    "mkd": "Macedonian",
    "mal": "Malayalam",
    "mar": "Marathi",
    "msa": "Malay",
    "mlt": "Maltese",
    "nep": "Nepali",
    "nor": "Norwegian",
    "ori": "Oriya",
    "pan": "Panjabi; Punjabi",
    "fas": "Persian",
    "pol": "Polish",
    "por": "Portuguese",
    "pus": "Pushto; Pashto",
    "ron": "Romanian; Moldavian; Moldovan",
    "rus": "Russian",
    "san": "Sanskrit",
    "srp": "Serbian",
    "srp_latn": "Serbian - Latin",
    "sin": "Sinhala; Sinhalese",
    "slk": "Slovak",
    "slv": "Slovenian",
    "spa": "Spanish; Castilian",
    "spa_old": "Spanish; Castilian - Old",
    "swa": "Swahili",
    "swe": "Swedish",
    "syr": "Syriac",
    "tgl": "Tagalog",
    "tgk": "Tajik",
    "tam": "Tamil",
    "tel": "Telugu",
    "tha": "Thai",
    "bod": "Tibetan",
    "tir": "Tigrinya",
    "tur": "Turkish",
    "uig": "Uighur; Uyghur",
    "ukr": "Ukrainian",
    "urd": "Urdu",
    "uzb": "Uzbek",
    "uzb_cyrl": "Uzbek - Cyrillic",
    "vie": "Vietnamese",
    "cym": "Welsh",
    "yid": "Yiddish",
}
PYTESSERACT_ALLOWED_LANGUAGES = LANGUAGE_CODES.keys()

PYLENIUM_CONFIG = os.path.join(SITE_ROOT_DIR, "pylenium.json")

MAINTENANCE_MODE_STATE_BACKEND = "maintenance_mode.backends.CacheBackend"
MAINTENANCE_MODE_IGNORE_ADMIN_SITE = True
MAINTENANCE_MODE_IGNORE_URLS = ("/healthz*", "/metrics*", "/maintenance-mode*")

DEFAULT_AXE_SCRIPT = os.path.join(
    SITE_ROOT_DIR, "node_modules", "axe-core", "axe.min.js"
)

# Used for tracking accepts for the review rate limit
TRANSCRIPTION_ACCEPTED_TRACKING_KEY = "TRANSCRIPTION_ACCEPTED_{user_id}"

CONFIGURATION_CACHE_TIMEOUT = 3600  # One hour

# The number of assets to store for next_transcribabe/next_reviewable, per campaign
NEXT_TRANSCRIBABE_ASSET_COUNT = 100
NEXT_REVIEWABLE_ASSET_COUNT = NEXT_TRANSCRIBABE_ASSET_COUNT
