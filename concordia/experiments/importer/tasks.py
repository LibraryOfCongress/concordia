# Create your tasks here
from __future__ import absolute_import, unicode_literals
from celery import shared_task
from .models import Importer

"""
Usage:
concordia (ENV)$ celery -A concordia worker -l info
concordia (ENV)$ python ./manage.py shell
>>> from concordia.tasks import downloader
>>> res = downloader.delay()
>>> res.get()
"""


@shared_task
def download():
    importer = Importer()
    importer.main()


@shared_task
def add(x, y):
    return x + y
