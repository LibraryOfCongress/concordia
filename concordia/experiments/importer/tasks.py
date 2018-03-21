from __future__ import absolute_import, unicode_literals
from celery import shared_task
from .models import Importer

"""
Pre-requisites:

 * AWS S3 bucket created and keys in ~/.aws/credentials
 * Configuration in env.ini "importer" section
 * RabbitMQ server running on localhost

Usage:

concordia (ENV)$ celery -A concordia worker -l info
concordia (ENV)$ python ./manage.py shell
>>> from concordia.experiments.importer.tasks import download, check_completeness, re_download
>>> res = download.delay() # Kicks off the download process
>>> res.get() # Won't return until download is complete - takes hours / days
>>> res = check_completeness.delay()
>>> while(res.get()==False)
...    res2 = re_download.delay()
...    res2.get()
...    res = check_completeness.delay()
>>>

"""


@shared_task
def download():
    importer = Importer()
    importer.main()


@shared_task
def check_completeness():
    importer = Importer()
    importer.check_completeness()
