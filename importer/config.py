"""
Importer app level configurations
"""

import os

IMPORTER = {"IMAGES_FOLDER": "/tmp/concordia_images/"}

IMPORTER_AWS_S3 = {
    "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID"),
    "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY"),
    "S3_BUCKET_NAME": "test-campaigns-bucket",
}
