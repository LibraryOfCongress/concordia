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
