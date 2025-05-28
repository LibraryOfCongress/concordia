from functools import wraps
from logging import getLogger

from django.utils.timezone import now

from importer import models
from importer.exceptions import ImageImportFailure

logger = getLogger(__name__)


def update_task_status(f):
    """
    Decorator which causes any function which is passed a TaskStatusModel
    subclass object to update on entry and exit and populate the status field
    with an exception message if raised

    Assumes that all wrapped functions get the Celery task self value as the
    first parameter and the TaskStatusModel subclass object as the second
    """

    @wraps(f)
    def inner(self, task_status_object, *args, **kwargs):
        # We'll do a sanity check to make sure that another process hasn't
        # updated the object status in the meantime:
        guard_qs = task_status_object.__class__._default_manager.filter(
            pk=task_status_object.pk, completed__isnull=False
        )
        if guard_qs.exists():
            logger.warning(
                "Task %s was already completed and will not be repeated",
                task_status_object,
                extra={
                    "data": {
                        "object": task_status_object,
                        "args": args,
                        "kwargs": kwargs,
                    }
                },
            )
            return

        task_status_object.last_started = now()
        task_status_object.task_id = self.request.id
        task_status_object.save()
        try:
            result = f(self, task_status_object, *args, **kwargs)
            task_status_object.completed = now()
            task_status_object.failed = None
            task_status_object.failure_reason = ""
            task_status_object.update_status("Completed")
            return result
        except Exception as exc:
            new_status = "{}\n\nUnhandled exception: {}".format(
                task_status_object.status, exc
            ).strip()
            task_status_object.update_status(new_status, do_save=False)
            task_status_object.failed = now()
            if isinstance(exc, ImageImportFailure):
                task_status_object.failure_reason = (
                    models.TaskStatusModel.FailureReason.IMAGE
                )
            task_status_object.save()
            retry_result = task_status_object.retry_if_possible()
            if retry_result:
                task_status_object.last_started = now()
                task_status_object.task_id = retry_result.id
                task_status_object.save()
            else:
                logger.info("Retrying task %s was not possible", task_status_object)
            raise

    return inner
