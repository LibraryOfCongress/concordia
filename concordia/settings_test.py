from .settings_template import *

LOGGING["handlers"]["stream"]["level"] = "INFO"
LOGGING["handlers"]["file"]["level"] = "INFO"
LOGGING["handlers"]["file"]["filename"] = "./logs/concordia-web.log"
LOGGING["handlers"]["celery"]["level"] = "INFO"
LOGGING["handlers"]["celery"]["filename"] = "./logs/concordia-celery.log"
LOGGING["loggers"]["django"]["level"] = "INFO"
LOGGING["loggers"]["celery"]["level"] = "INFO"

DEBUG = False

DATABASES["default"].update({"PASSWORD": "", "USER": "postgres"})

DEFAULT_TO_EMAIL = "rstorey@loc.gov"

ALLOWED_HOSTS = ["127.0.0.1", "0.0.0.0"]

EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

SESSION_ENGINE = "django.contrib.sessions.backends.cache"

RATELIMIT_ENABLE = False
