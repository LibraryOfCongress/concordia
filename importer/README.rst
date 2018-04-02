Importer
========

This is a Django app which uses celery to download images from a collection on loc.gov.
It also uploads those images to an S3 bucket.

Pre-requisites:
- AWS S3 bucket created and keys in ~/.aws/credentials
- Configuration in env.ini "importer" and "celery" sections
- RabbitMQ server running on localhost or in docker container
- http access to tile-dev.loc.gov and dev.loc.gov

Usage:
::
concordia (ENV)$ celery -A importer.importer worker -l info
concordia (ENV)$ python ./manage.py shell
>>> from importer.importer.tasks import download, check_completeness
>>> res = download.delay() # Kicks off the download process
>>> res.get() # Won't return until download is complete - takes hours / days
>>> res = check_completeness.delay()
>>> while(res.get()==False)
...    res2 = download.delay()
...    res2.get()
...    res = check_completeness.delay()
>>>
::