from concordia.celery import app as concordia_celery_app


def get_registered_task(name):
    """
    Retrieve a Celery task by its fully qualified name.

    This function looks up a task in the Celery app's task registry.
    It raises a RuntimeError if the task is not found.
    The purpose of this function is to provide a useable interface for
    safely calling a task without needing to import it (to avoid issues like)
    circular imports. This avoids issues with app.send_task, which ignores
    things like the ALWAYS_EAGER setting.

    Args:
        name (str): The fully qualified task name (e.g., 'myapp.tasks.my_task').

    Returns:
        celery.Task: The registered Celery task object.

    Raises:
        RuntimeError: If the task name is not found in the registry.
    """
    try:
        return concordia_celery_app.tasks[name]
    except KeyError as err:
        raise RuntimeError(f"Task {name} is not registered. Did you typo it?") from err
