from __future__ import absolute_import, unicode_literals

# This will make sure the app is always imported when
# Django starts so that shared_task will use this app.
from importer.importer.celery import app as celery_app

__all__ = ['celery_app']

VERSION = (0, 0, 1)
def get_version():
    return '.'.join(map(str, VERSION))
