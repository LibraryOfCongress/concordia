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
        "USER": "concordia",
        "PASSWORD": "post12345",
        "HOST": "0.0.0.0",
        "PORT": "54321",
    }
}

ALLOWED_HOSTS = ["127.0.0.1", "0.0.0.0", "*"]

CELERY_BROKER_URL = "amqp://"

CONCORDIA = {"netloc": "http://0:80"}

IMPORTER = {
    "BASE_URL": "",
    "IMAGES_FOLDER": "/tmp/concordia_images/",
    "ITEM_COUNT": "",
    "S3_BUCKET_NAME": "",
}

EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
EMAIL_FILE_PATH = "/tmp/concordia-messages"  # change this to a proper location
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "")
DEFAULT_TO_EMAIL = DEFAULT_FROM_EMAIL
