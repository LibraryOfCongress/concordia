from logging import getLogger

from django.core.management import call_command

from concordia.logging import ConcordiaLogger

from ..celery import app as celery_app

logger = getLogger(__name__)
structured_logger = ConcordiaLogger.get_logger(__name__)


@celery_app.task
def create_opensearch_indices():
    """
    Create OpenSearch indices if they do not already exist.

    This task invokes the ``opensearch index create`` management command with
    ``verbosity=2``, ``force=True`` and ``ignore_error=True``.
    """
    call_command(
        "opensearch", "index", "create", verbosity=2, force=True, ignore_error=True
    )


@celery_app.task
def delete_opensearch_indices():
    """
    Delete OpenSearch indices and their stored documents.

    This task invokes the ``opensearch index delete`` management command with
    ``force=True`` and ``ignore_error=True``.
    """
    call_command("opensearch", "index", "delete", force=True, ignore_error=True)


@celery_app.task
def rebuild_opensearch_indices():
    """
    Rebuild all OpenSearch indices.

    This task invokes the ``opensearch index rebuild`` management command with
    ``verbosity=2``, ``force=True`` and ``ignore_error=True``.
    """
    call_command(
        "opensearch", "index", "rebuild", verbosity=2, force=True, ignore_error=True
    )


@celery_app.task
def populate_opensearch_users_indices():
    """
    Populate the ``users`` OpenSearch index.

    This task invokes the ``opensearch document index`` management command for
    the ``users`` index with ``--force`` and ``--parallel`` so user documents
    defined by the `UserDocument` mapping are indexed and searchable in
    OpenSearch Dashboards.
    """
    call_command(
        "opensearch", "document", "index", "--indices", "users", "--force", "--parallel"
    )


@celery_app.task
def populate_opensearch_assets_indices():
    """
    Populate the ``assets`` OpenSearch index.

    This task invokes the ``opensearch document index`` management command for
    the ``assets`` index with ``--force`` and ``--parallel`` so asset documents
    defined by the `AssetDocument` mapping are indexed and searchable in
    OpenSearch Dashboards.
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
    Populate all OpenSearch document indices.

    This task invokes the ``opensearch document index`` management command with
    ``--force`` to skip interactive confirmation and ``--parallel`` to index
    documents in parallel.
    """
    call_command("opensearch", "document", "index", "--force", "--parallel")
