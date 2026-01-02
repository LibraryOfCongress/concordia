from functools import wraps
from logging import getLogger
from typing import Any, Callable, Concatenate, ParamSpec, TypeVar

from celery import Task
from django.utils.timezone import now

from importer import models
from importer.exceptions import ImageImportFailure

logger = getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def update_task_status(
    f: Callable[Concatenate[Task, Any, P], R],
) -> Callable[Concatenate[Task, Any, P], R]:
    """
    Decorator to track lifecycle and failure state for a task-like function.

    The wrapped function must take the Celery task self as the first argument
    and a TaskStatusModel instance as the second argument. On entry records
    last_started and task_id. On success sets completed and clears failure
    fields. On exception updates status, marks failed, sets failure_reason for
    known error types, saves the model, then attempts retry_if_possible before
    re-raising.

    Also guards against re-running a task already marked completed.

    Args:
        f: The function to wrap. Must accept
           ``(self, task_status_object, *args, **kwargs)``.

    Returns:
        A callable with the same signature as ``f``.
    """

    @wraps(f)
    def inner(
        self: Task, task_status_object: Any, *args: P.args, **kwargs: P.kwargs
    ) -> R:
        # Sanity guard: if another worker already completed this task, skip work.
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
            return  # noqa: RET504

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
