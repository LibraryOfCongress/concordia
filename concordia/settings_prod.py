from settings_template import *
 
LOGGING["handlers"]["stream"]["level"] = "INFO"
LOGGING["handlers"]["file"]["level"] = "INFO"
LOGGING["handlers"]["file"]["filename"] = "/var/log/django/concordia-web.log"
LOGGING["handlers"]["celery"]["level"] = "INFO"
LOGGING["handlers"]["celery"]["filename"] = "/var/log/django/concordia-celery.log"
LOGGING["loggers"]["django"]["level"] = "INFO"
LOGGING["loggers"]["celery"]["level"] = "INFO"

DJANGO_SECRET_KEY = "np*no_id-t8*if4*a(pz(n(rk5#(rlyn-41jvp5u%*ij&5u-3x"

# TODO: For final deployment to production, when we are running https, uncomment this next line
# CSRF_COOKIE_SECURE = True

IMPORTER = {
    "BASE_URL"       :   "",
    "IMAGES_FOLDER"  :   "/app/",
    "ITEM_COUNT"     :   "",
    "S3_BUCKET_NAME" :   ""
}