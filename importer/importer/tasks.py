from __future__ import absolute_import, unicode_literals
from celery import shared_task
from importer.importer.models import Importer


@shared_task
def download():
    importer = Importer()
    importer.main()


@shared_task
def check_completeness():
    importer = Importer()
    importer.check_completeness()
