from unittest.mock import MagicMock, patch

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from .utils import create_asset


class S3StorageAPITest(TestCase):
    def setUp(self):
        super().setUp()
        # Reset ASSET_STORAGE so it's evaluated with
        # the new settings
        from concordia.storage import ASSET_STORAGE

        ASSET_STORAGE._wrapped = None

    def tearDown(self):
        # Reset ASSET_STORAGE so it doesn't keep
        # the overriden settings in future tests
        from concordia.storage import ASSET_STORAGE

        ASSET_STORAGE._wrapped = None
        ASSET_STORAGE._setup()
        super().tearDown()

    @override_settings(
        STORAGES={
            "default": {
                "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
            },
            "assets": {
                "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
                "OPTIONS": {
                    "querystring_auth": False,
                },
            },
        },
        AWS_STORAGE_BUCKET_NAME="test-bucket",
    )
    @patch("botocore.auth.SigV4Auth.add_auth")
    @patch("botocore.endpoint.Endpoint._send")
    def test_s3_upload_api_layer(self, mock_send, mock_add_auth):
        # Set up mocked response to prevent real network call
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.content = b""
        mock_send.return_value = mock_response

        # We import this here to stop it from being
        # evaluated before we override the storage settings
        from concordia.storage import ASSET_STORAGE

        ASSET_STORAGE._setup()

        # Simulate manually saving to the storage backend
        asset_image_filename = "test-campaign/test-project/1.jpg"
        content = ContentFile(b"abc123", name="test.jpg")

        ASSET_STORAGE.save(asset_image_filename, content)
        asset = create_asset(storage_image=asset_image_filename)

        self.assertTrue(asset.storage_image.name.endswith("1.jpg"))
        mock_send.assert_called()
