import os.path
from logging import getLogger

import boto3
from django.conf import settings

from concordia.logging import ConcordiaLogger
from concordia.models import ResourceFile

from ..celery import app as celery_app

logger = getLogger(__name__)
structured_logger = ConcordiaLogger.get_logger(__name__)


@celery_app.task(ignore_result=True)
def populate_resource_files():
    """
    Synchronize ResourceFile records with S3 objects under the resources prefix.

    This task lists all objects in the S3 bucket specified by
    ``settings.S3_BUCKET_NAME`` whose keys begin with
    ``"cm-uploads/resources/"``. For each object (excluding the bare prefix
    placeholder key), it ensures that a corresponding :class:`ResourceFile`
    exists.

    For any S3 key that does not already have a matching ``ResourceFile``
    (by ``resource`` field), a new record is created with:

    * ``resource`` set to the full S3 key.
    * ``name`` derived from the filename and extension, in the form
      ``"<filename>-<extension>"`` (for example, ``"guide-pdf"``).

    Existing records are left unchanged, making this task safe to run
    repeatedly to backfill or resynchronize metadata from S3.
    """
    client = boto3.client("s3")
    response = client.list_objects_v2(
        Bucket=settings.S3_BUCKET_NAME, Prefix="cm-uploads/resources/"
    )
    files = response["Contents"]
    for file in files:
        path = file["Key"]
        if path == "cm-uploads/resources/":
            continue
        try:
            ResourceFile.objects.get(resource=path)
        except ResourceFile.DoesNotExist:
            filename, extension = os.path.splitext(os.path.basename(path))
            name = "%s-%s" % (filename, extension[1:])
            ResourceFile.objects.create(resource=path, name=name)
