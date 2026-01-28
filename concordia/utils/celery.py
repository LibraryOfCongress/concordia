from celery import Task

from concordia.celery import app as concordia_celery_app


def get_registered_task(name: str) -> Task:
    """
    Retrieve a Celery task by its fully qualified name.

    This function looks up a task in the Celery app task registry. It raises a
    RuntimeError if the task is not found. The purpose of this function is to
    provide a usable interface for safely calling a task without importing it
    directly, to avoid issues such as circular imports. This avoids issues with
    `app.send_task`, which ignores settings such as `ALWAYS_EAGER`.

    Args:
        name (str): Fully qualified task name, for example
            "myapp.tasks.my_task".

    Returns:
        Task: The registered Celery task object.

    Raises:
        RuntimeError: If the task name is not found in the registry.
    """
    try:
        return concordia_celery_app.tasks[name]
    except KeyError as err:
        raise RuntimeError(f"Task {name} is not registered. Did you typo it?") from err
