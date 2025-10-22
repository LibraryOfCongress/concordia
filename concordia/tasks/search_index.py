from logging import getLogger

from django.core.management import call_command

from concordia.logging import ConcordiaLogger

from ..celery import app as celery_app

logger = getLogger(__name__)
structured_logger = ConcordiaLogger.get_logger(__name__)


@celery_app.task
def create_opensearch_indices():
    """Create the opensearch indices, if they don't already exist."""
    call_command(
        "opensearch", "index", "create", verbosity=2, force=True, ignore_error=True
    )


@celery_app.task
def delete_opensearch_indices():
    """Delete opensearch indices - index and data (a.k.a. documents)."""
    call_command("opensearch", "index", "delete", force=True, ignore_error=True)


@celery_app.task
def rebuild_opensearch_indices():
    """Deletes, then creates opensearch indices."""
    call_command(
        "opensearch", "index", "rebuild", verbosity=2, force=True, ignore_error=True
    )


@celery_app.task
def populate_opensearch_users_indices():
    """
    Populate the "users" OpenSearch index. This function loads the indices
    in Opensearch as defined in the UserDocument class to make it searchable
    and accessible for queries in the Opensearch Dashboards.
    """
    call_command(
        "opensearch", "document", "index", "--indices", "users", "--force", "--parallel"
    )


@celery_app.task
def populate_opensearch_assets_indices():
    """
    Populate the "assets" OpenSearch index. This function loads the indices
    in Opensearch as defined in the AssetDocument class to make it searchable
    and accessible for queries in the Opensearch Dashboards.
    """
    call_command(
        "opensearch",
        "document",
        "index",
        "--indices",
        "assets",
        "--force",
        "--parallel",
    )


@celery_app.task
def populate_opensearch_indices():
    """
    Populate the OpenSearch index with all documents.
    --force - stops interactive confirmation prompt.
    --parallel - invokes opensearch in parallel mode.
    """
    call_command("opensearch", "document", "index", "--force", "--parallel")
