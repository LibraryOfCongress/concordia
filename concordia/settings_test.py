from .settings_template import *

LOGGING["handlers"]["stream"]["level"] = "DEBUG"
LOGGING["handlers"]["file"]["level"] = "DEBUG"
LOGGING["handlers"]["file"]["filename"] = "./logs/concordia-web.log"
LOGGING["handlers"]["celery"]["level"] = "DEBUG"
LOGGING["handlers"]["celery"]["filename"] = "./logs/concordia-celery.log"
LOGGING["loggers"]["django"]["level"] = "DEBUG"
LOGGING["loggers"]["celery"]["level"] = "DEBUG"

DEBUG = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "concordia",
        "USER": "postgres",
        "PASSWORD": "concordia",
        "HOST": "0.0.0.0",
        "PORT": "5432",
    }
}

DEFAULT_TO_EMAIL = "rstorey@loc.gov"

ALLOWED_HOSTS = ["127.0.0.1", "0.0.0.0"]

CONCORDIA = {"netloc": "http://0.0.0.0:8000"}

EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"
