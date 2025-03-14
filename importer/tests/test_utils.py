import uuid
from unittest import mock

from django.test import TestCase

from concordia.tests.utils import create_asset
from importer.models import VerifyAssetImageJob
from importer.utils import create_verify_asset_image_job_batch


class CreateVerifyAssetImageJobBatchTests(TestCase):
    def setUp(self):
        self.batch_id = uuid.uuid4()
        self.asset = create_asset()
        self.assets = [self.asset] + [
            create_asset(item=self.asset.item, slug=f"test-asset-{i}")
            for i in range(1, 5)
        ]
        self.asset_pks = [asset.pk for asset in self.assets]

    @mock.patch("importer.tasks.batch_verify_asset_images_task.delay")
    def test_create_jobs_single_batch(self, mock_task):
        job_count, batch_url = create_verify_asset_image_job_batch(
            self.asset_pks, self.batch_id
        )

        self.assertEqual(job_count, 5)
        self.assertEqual(
            VerifyAssetImageJob.objects.filter(batch=self.batch_id).count(), 5
        )
        mock_task.assert_called_once_with(batch=self.batch_id)
        self.assertEqual(
            batch_url, VerifyAssetImageJob.get_batch_admin_url(self.batch_id)
        )

    @mock.patch("importer.tasks.batch_verify_asset_images_task.delay")
    def test_create_jobs_multiple_batches(self, mock_task):
        asset_pks = self.asset_pks + [
            asset.pk
            for asset in [
                create_asset(item=self.asset.item, slug=f"test-asset-{i}")
                for i in range(5, 150)
            ]
        ]
        job_count, _ = create_verify_asset_image_job_batch(asset_pks, self.batch_id)

        self.assertEqual(job_count, 150)
        self.assertEqual(
            VerifyAssetImageJob.objects.filter(batch=self.batch_id).count(), 150
        )
        mock_task.assert_called_once_with(batch=self.batch_id)

    @mock.patch("importer.tasks.batch_verify_asset_images_task.delay")
    def test_no_assets_provided(self, mock_task):
        job_count, batch_url = create_verify_asset_image_job_batch([], self.batch_id)

        self.assertEqual(job_count, 0)
        self.assertEqual(
            VerifyAssetImageJob.objects.filter(batch=self.batch_id).count(), 0
        )
        mock_task.assert_called_once_with(batch=self.batch_id)
        self.assertEqual(
            batch_url, VerifyAssetImageJob.get_batch_admin_url(self.batch_id)
        )
