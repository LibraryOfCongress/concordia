from .settings_template import *

LOGGING["handlers"]["stream"]["level"] = "DEBUG"
LOGGING["handlers"]["file"]["level"] = "DEBUG"
LOGGING["handlers"]["file"]["filename"] = "./concordia-web.log"
LOGGING["handlers"]["celery"]["level"] = "DEBUG"
LOGGING["handlers"]["celery"]["filename"] = "./concordia-celery.log"
LOGGING["loggers"]["django"]["level"] = "DEBUG"
LOGGING["loggers"]["celery"]["level"] = "DEBUG"

DEBUG = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": "concordia",
        "USER": "concordia",
        "PASSWORD": "concordia",
        "HOST": "0.0.0.0",
        "PORT": "54321",
    }
}

ALLOWED_HOSTS = ["127.0.0.1","0.0.0.0"]

CELERY_BROKER_URL = "amqp://"
 
CONCORDIA = dict(netloc="http://0.0.0.0:8000") 
 

IMPORTER = {
    "BASE_URL"       :   "",
    "IMAGES_FOLDER"  :   "/concordia_images/",
    "ITEM_COUNT"     :   "",
    "S3_BUCKET_NAME" :   ""
}