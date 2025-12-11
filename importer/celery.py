import importlib
import pkgutil

from celery import Celery

app = Celery("importer")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()


def import_all_submodules(package_name: str):
    """
    Import a package and recursively import all submodules.
    Used sparingly at Celery startup to ensure all task modules are loaded.
    """
    pkg = importlib.import_module(package_name)
    if not hasattr(pkg, "__path__"):
        return
    for mod in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
        importlib.import_module(mod.name)


# Import all task modules under these packages
# We do this because celery autodiscovery won't
# find anything not in tasks.py or tasks/__init__.py
# We need to defer this until after Django is fully loaded
@app.on_after_finalize.connect
def _load_all_task_modules(sender, **kwargs):
    import_all_submodules("concordia.tasks")
    import_all_submodules("importer.tasks")
