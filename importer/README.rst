Importer
========

This is a Django app which uses celery to download images from a collection on loc.gov.
It also uploads those images to an S3 bucket.

Pre-requisites:
 - If uploading to S3 bucket, AWS S3 bucket created and keys in ~/.aws/credentials
 - If running in dev mode, HTTP access to tile-dev.loc.gov and dev.loc.gov


Usage
-----

 >>> concordia$ docker-compose up
 >>> concordia$ docker exec -it concordia_importer_1 bash
 root@62e3ebef4de2:/app# python3 ./manage.py shell
 Python 3.6.5rc1 (default, Mar 14 2018, 06:54:23) [GCC 7.3.0] on linux
 Type "help", "copyright", "credits" or "license" for more information.
 >>> from importer.importer.tasks import download_async_collection, check_completeness
 >>> result = download_async_collection.delay("https://www.loc.gov/collections/clara-barton-papers/?fa=partof:clara+barton+papers:++diaries+and+journals,+1849-1911")
 >>> result.ready()
 >>> result.get()
 >>> result2 = check_completeness.delay()
 >>> result2.ready()
 >>> result2.get()


To count the files and check disk usage in /concordia_images after download is complete:

 >>> docker exec -it concordia_app_1 bash
 >>> find /concordia_images -type f | wc -l
 >>> df -kh

