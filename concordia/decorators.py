# Based on code from https://gist.github.com/dmwyatt/d09da3f03cbdcad217db35f5cf8a9f94
import hashlib
import logging
from functools import wraps

from celery import Task

from concordia.contextmanagers import cache_lock

logger = logging.getLogger(__name__)


def locked_task(function=None, lock_by_args: bool = True):
    """
    Decorator to lock a task from concurrent execution.
    This requires the task to be bound (bind=True) and for the
    task decorate to be above this decorator.
    ## Locking by task + arguments
    Allows duplicate calls of the task as long as each call uses different arguments.
    >>> from celery.task import task
    >>> @task(bind=True)
    ... @locked_task        # <=========== Note no-arg version of decorator
    ... def a_task(self, some_arg):
    ...     time.sleep(10)
    Start a task.
    >>> a_task.delay("foo")
    Try to start task with same args again. Nothing happens since it was just called
    with those args and it's still running
    >>> a_task.delay("foo")
    Will run even though first call started task since this call has different args.
    >>> a_task.delay("bar")

    ## Locking by task
    Lock task against concurrent calls regardless of arguments
    >>> @task(bind=True)
    ... @locked_task(lock_by_args=False)        # <=========== Note `lock_by_args`
    ... def a_task(self, some_arg):
    ...     time.sleep(10)

    ## Forcing a run
    You can force the task to run regardless of the lock by passing force=True
    This is most useful if a lock is "stuck" or if you have a case where you don't
    care about the lock
    This can be used when directly (synchronously) calling the task and through
    kwargs with apply_async. It cannot be used with delay.
    >>> a_task(some_arg, force=True)
    >>> a_task.apply_async(args=(some_arg,), kwargs={'force' : True})
    """

    def decorator(f):
        @wraps(f)
        def wrapped(self: Task, *args, **kwargs):
            force = kwargs.pop("force", False)  # Remove 'force' before passing to task

            if lock_by_args:
                # lock with name of function and its hashed arguments.  This
                # means that if any of the function, args or kwargs are
                # different, then the lock won't match and another instance
                # of the task will run
                try:
                    # We hash the arguments to make them safe for use as a cache key
                    raw_key = f"{repr(args)}:{repr(sorted(kwargs.items()))}"
                    key = f"{self.name}:{hashlib.sha256(raw_key.encode()).hexdigest()}"
                except Exception:
                    logger.exception(
                        "Unable to create cache key from arguments for %s.", self.name
                    )
                    raise

            else:
                # Use name of task as key.
                key = self.name

            with cache_lock(key, self.request.hostname) as acquired:
                if acquired or force:
                    if not acquired:
                        logger.warning(
                            "Force-running task %s with key %s; lock not acquired",
                            self.name,
                            key,
                        )
                    return f(self, *args, **kwargs)
                logger.info(
                    "Task %s with key %s is already running; skipping", self.name, key
                )

        return wrapped

    return decorator(function) if function else decorator
