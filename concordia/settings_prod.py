from .settings_template import *
 
LOGGING["handlers"]["stream"]["level"] = "INFO"
LOGGING["handlers"]["file"]["level"] = "INFO"
LOGGING["handlers"]["file"]["filename"] = "./logs/concordia-web.log"
LOGGING["handlers"]["celery"]["level"] = "INFO"
LOGGING["handlers"]["celery"]["filename"] = "./logs/concordia-celery.log"
LOGGING["loggers"]["django"]["level"] = "INFO"
LOGGING["loggers"]["celery"]["level"] = "INFO"

DJANGO_SECRET_KEY = "changeme"

# TODO: For final deployment to production, when we are running https, uncomment this next line
# CSRF_COOKIE_SECURE = True

IMPORTER = {
    "BASE_URL"       :   "",
    # /concordia_images is a docker volume shared by importer and concordia    
    "IMAGES_FOLDER"  :   "/concordia_images/",
    "ITEM_COUNT"     :   "",
    "S3_BUCKET_NAME" :   ""
}
