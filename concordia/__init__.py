from __future__ import absolute_import, unicode_literals

from concordia.celery import app as celery_app

__all__ = ["celery_app"]


VERSION = (0, 0, 1)


def get_version():
    return ".".join(map(str, VERSION))
