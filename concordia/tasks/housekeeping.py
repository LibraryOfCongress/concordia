from logging import getLogger

from django.core.management import call_command

from concordia.logging import ConcordiaLogger

from ..celery import app as celery_app

logger = getLogger(__name__)
structured_logger = ConcordiaLogger.get_logger(__name__)


@celery_app.task(ignore_result=True)
def clear_sessions():
    # This clears expired Django sessions in the database
    call_command("clearsessions")
