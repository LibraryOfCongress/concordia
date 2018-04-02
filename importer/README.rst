Importer
========

This is a Django app which uses celery to download images from a collection on loc.gov.
It also uploads those images to an S3 bucket.

Pre-requisites:
 - AWS S3 bucket created and keys in ~/.aws/credentials (if uploading to S3 bucket)
 - Configuration in env.ini "importer" and "celery" sections
 - RabbitMQ server running on localhost or in docker container
 - http access to tile-dev.loc.gov and dev.loc.gov


Usage
-----

 >>> concordia$ docker exec -it concordia_importer_1 bash
 root@62e3ebef4de2:/app# python3 ./manage.py shell
 Python 3.6.5rc1 (default, Mar 14 2018, 06:54:23) [GCC 7.3.0] on linux
 Type "help", "copyright", "credits" or "license" for more information.
 >>> from importer.importer.tasks import download_async_collection
 >>> result=download_async_collection(collection_url)
 >>>
