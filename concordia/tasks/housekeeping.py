from logging import getLogger

from django.core.management import call_command

from concordia.logging import ConcordiaLogger

from ..celery import app as celery_app

logger = getLogger(__name__)
structured_logger = ConcordiaLogger.get_logger(__name__)


@celery_app.task(ignore_result=True)
def clear_sessions():
    """
    Clear expired Django session records.

    This Celery task runs Django's ``clearsessions`` management command to
    remove expired rows from the session store. It is typically invoked on a
    schedule to prevent the session table from growing without bounds.
    """
    call_command("clearsessions")
