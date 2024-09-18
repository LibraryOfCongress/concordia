import os

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

# Turnstile settings
TURNSTILE_JS_API_URL = os.environ.get(
    "TURNSTILE_JS_API_URL", "https://challenges.cloudflare.com/turnstile/v0/api.js"
)
TURNSTILE_VERIFY_URL = os.environ.get(
    "TURNSTILE_VERIFY_URL", "https://challenges.cloudflare.com/turnstile/v0/siteverify"
)
TURNSTILE_SITEKEY = os.environ.get(
    "TURNSTILE_SITEKEY", "1x00000000000000000000BB"
)  # Always pass, invisible
TURNSTILE_SECRET = os.environ.get(
    "TURNSTILE_SECRET", "1x0000000000000000000000000000000AA"
)  # Always pass
