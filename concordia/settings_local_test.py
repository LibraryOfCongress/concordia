from .settings_template import *  # NOQA ignore=F405
from .settings_template import DATABASES

DEBUG = False

DATABASES["default"]["PORT"] = "54323"

DEFAULT_TO_EMAIL = "rsar@loc.gov"

ALLOWED_HOSTS = ["127.0.0.1", "0.0.0.0"]  # nosec

EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"

SESSION_ENGINE = "django.contrib.sessions.backends.cache"

RATELIMIT_ENABLE = False

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [("localhost", 63791)]},
    }
}
