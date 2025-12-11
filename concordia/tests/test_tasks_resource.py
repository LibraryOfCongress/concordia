from unittest import mock

from django.test import TestCase, override_settings

from concordia.models import ResourceFile
from concordia.tasks.resource import populate_resource_files


class PopulateResourceFilesTaskTests(TestCase):
    @override_settings(S3_BUCKET_NAME="unit-bucket")
    def test_creates_missing_resources_and_builds_name(self):
        # List two real files; both should be created with derived names.
        with mock.patch("concordia.tasks.resource.boto3.client") as m_client:
            fake_client = mock.MagicMock()
            m_client.return_value = fake_client
            fake_client.list_objects_v2.return_value = {
                "Contents": [
                    {"Key": "cm-uploads/resources/doc1.pdf"},
                    {"Key": "cm-uploads/resources/image.png"},
                ]
            }

            populate_resource_files()

            m_client.assert_called_once_with("s3")
            fake_client.list_objects_v2.assert_called_once_with(
                Bucket="unit-bucket", Prefix="cm-uploads/resources/"
            )

        rf1 = ResourceFile.objects.get(resource="cm-uploads/resources/doc1.pdf")
        self.assertEqual(rf1.name, "doc1-pdf")

        rf2 = ResourceFile.objects.get(resource="cm-uploads/resources/image.png")
        self.assertEqual(rf2.name, "image-png")

    @override_settings(S3_BUCKET_NAME="unit-bucket")
    def test_skips_existing_resource(self):
        # Precreate one resource; task must not create a duplicate.
        existing_path = "cm-uploads/resources/existing.pdf"
        ResourceFile.objects.create(resource=existing_path, name="existing-pdf")

        with mock.patch("concordia.tasks.resource.boto3.client") as m_client:
            fake_client = mock.MagicMock()
            m_client.return_value = fake_client
            fake_client.list_objects_v2.return_value = {
                "Contents": [{"Key": existing_path}]
            }

            populate_resource_files()

        self.assertEqual(ResourceFile.objects.filter(resource=existing_path).count(), 1)

    @override_settings(S3_BUCKET_NAME="unit-bucket")
    def test_ignores_root_prefix_entry(self):
        # Include the bare prefix key; it must be ignored by the loop.
        prefix_key = "cm-uploads/resources/"
        real_key = "cm-uploads/resources/new.txt"

        with mock.patch("concordia.tasks.resource.boto3.client") as m_client:
            fake_client = mock.MagicMock()
            m_client.return_value = fake_client
            fake_client.list_objects_v2.return_value = {
                "Contents": [{"Key": prefix_key}, {"Key": real_key}]
            }

            populate_resource_files()

        self.assertFalse(ResourceFile.objects.filter(resource=prefix_key).exists())
        self.assertTrue(
            ResourceFile.objects.filter(resource=real_key, name="new-txt").exists()
        )
