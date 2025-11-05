import uuid
from unittest import mock

import requests
from django.test import TestCase
from django.utils import timezone
from PIL import Image

from concordia.models import Asset
from concordia.tests.utils import (
    create_asset,
)
from importer import tasks
from importer.models import (
    DownloadAssetImageJob,
    VerifyAssetImageJob,
)
from importer.tasks.images import redownload_image_task

from .utils import (
    create_download_asset_image_job,
    create_verify_asset_image_job,
)


class RedownloadImageTaskTests(TestCase):
    @mock.patch("importer.tasks.images.download_asset")
    def test_redownload_image_task(self, mock_download):
        redownload_image_task(create_asset().pk)
        self.assertTrue(mock_download.called)


class BatchVerifyAssetImagesTaskCallbackTests(TestCase):
    def setUp(self):
        self.batch_id = uuid.uuid4()
        self.concurrency = 5

    @mock.patch("importer.tasks.images.batch_verify_asset_images_task.delay")
    def test_no_failures_detected_no_failures_in_results(self, mock_task):
        results = [True, True, True]
        tasks.images.batch_verify_asset_images_task_callback(
            results, self.batch_id, self.concurrency, False
        )
        mock_task.assert_called_once_with(self.batch_id, self.concurrency, False)

    @mock.patch("importer.tasks.images.batch_verify_asset_images_task.delay")
    def test_no_failures_detected_some_failures_in_results(self, mock_task):
        results = [True, False, True]
        with self.assertLogs("importer.tasks", level="INFO") as log:
            tasks.images.batch_verify_asset_images_task_callback(
                results, self.batch_id, self.concurrency, False
            )
            self.assertIn(
                "INFO:importer.tasks.images:At least one verification "
                f"failure detected for batch {self.batch_id}",
                log.output,
            )
        mock_task.assert_called_once_with(self.batch_id, self.concurrency, True)

    @mock.patch("importer.tasks.images.batch_verify_asset_images_task.delay")
    def test_failures_already_detected(self, mock_task):
        results = [True, False, True]
        tasks.images.batch_verify_asset_images_task_callback(
            results, self.batch_id, self.concurrency, True
        )
        mock_task.assert_called_once_with(self.batch_id, self.concurrency, True)


class BatchVerifyAssetImagesTaskTests(TestCase):
    def setUp(self):
        self.batch_id = uuid.uuid4()
        self.concurrency = 2
        asset1 = create_asset()
        asset2 = create_asset(item=asset1.item, slug="test-asset-2")
        self.job1 = create_verify_asset_image_job(batch=self.batch_id, asset=asset1)
        self.job2 = create_verify_asset_image_job(batch=self.batch_id, asset=asset2)

    @mock.patch("importer.tasks.images.logger.info")
    @mock.patch("importer.tasks.images.batch_download_asset_images_task")
    def test_no_jobs_remaining_with_failures(self, mock_batch_download, mock_logger):
        VerifyAssetImageJob.objects.all().delete()
        tasks.images.batch_verify_asset_images_task(
            self.batch_id, self.concurrency, True
        )
        mock_logger.assert_any_call(
            "Failures in VerifyAssetImageJobs in batch %s detected, so starting "
            "DownloadAssetImageJob batch",
            self.batch_id,
        )
        mock_batch_download.assert_called_once_with(self.batch_id, self.concurrency)

    @mock.patch("importer.tasks.images.logger.info")
    def test_no_jobs_remaining_no_failures(self, mock_logger):
        VerifyAssetImageJob.objects.all().delete()
        tasks.images.batch_verify_asset_images_task(
            self.batch_id, self.concurrency, False
        )
        mock_logger.assert_any_call(
            "No failures in VerifyAssetImageJob batch %s. Ending task.", self.batch_id
        )

    @mock.patch("importer.tasks.images.chord")
    @mock.patch("importer.tasks.images.verify_asset_image_task.s")
    def test_jobs_remaining(self, mock_task_s, mock_chord):
        tasks.images.batch_verify_asset_images_task(
            self.batch_id, self.concurrency, False
        )
        self.assertEqual(mock_task_s.call_count, 2)
        mock_chord.assert_called()


class VerifyAssetImageTaskTests(TestCase):
    def setUp(self):
        self.asset = create_asset()
        self.batch_id = uuid.uuid4()

    @mock.patch("importer.tasks.images.logger.exception")
    def test_asset_not_found(self, mock_logger):
        with self.assertRaises(Asset.DoesNotExist):
            tasks.images.verify_asset_image_task(999)
        mock_logger.assert_called()

    @mock.patch("importer.tasks.images.logger.exception")
    def test_verify_job_not_found(self, mock_logger):
        with self.assertRaises(VerifyAssetImageJob.DoesNotExist):
            tasks.images.verify_asset_image_task(
                self.asset.pk, self.batch_id, create_job=False
            )
        mock_logger.assert_called()

    @mock.patch("importer.tasks.images.verify_asset_image")
    def test_verify_asset_image_task_success(self, mock_verify):
        job = create_verify_asset_image_job(asset=self.asset, batch=self.batch_id)
        mock_verify.return_value = True

        result = tasks.images.verify_asset_image_task(self.asset.pk, self.batch_id)
        self.assertTrue(result)
        job.refresh_from_db()
        self.assertEqual(job.status, "Storage image verified")

    @mock.patch("importer.tasks.images.verify_asset_image")
    def test_verify_asset_image_task_failure(self, mock_verify):
        job = create_verify_asset_image_job(asset=self.asset, batch=self.batch_id)
        mock_verify.return_value = False

        result = tasks.images.verify_asset_image_task(self.asset.pk, self.batch_id)
        self.assertFalse(result)
        job.refresh_from_db()
        self.assertNotEqual(job.status, "Storage image verified")

    @mock.patch("importer.tasks.images.verify_asset_image")
    def test_create_verify_asset_image_job(self, mock_verify):
        mock_verify.return_value = True
        result = tasks.images.verify_asset_image_task(
            self.asset.pk, self.batch_id, create_job=True
        )
        self.assertTrue(result)
        self.assertTrue(
            VerifyAssetImageJob.objects.filter(
                asset=self.asset, batch=self.batch_id
            ).exists()
        )

    @mock.patch("importer.tasks.images.verify_asset_image")
    def test_http_error_retries(self, mock_verify):
        create_verify_asset_image_job(asset=self.asset, batch=self.batch_id)
        mock_verify.side_effect = requests.exceptions.HTTPError("HTTP Error Occurred")
        with self.assertRaises(requests.exceptions.HTTPError):
            tasks.images.verify_asset_image_task(self.asset.pk, self.batch_id)


class CreateDownloadAssetImageJobTests(TestCase):
    def setUp(self):
        self.asset = create_asset()
        self.batch_id = uuid.uuid4()

    def test_create_new_job(self):
        tasks.images.create_download_asset_image_job(self.asset, self.batch_id)
        self.assertTrue(
            DownloadAssetImageJob.objects.filter(
                asset=self.asset, batch=self.batch_id
            ).exists()
        )

    def test_existing_uncompleted_job_not_duplicated(self):
        create_download_asset_image_job(asset=self.asset, batch=self.batch_id)
        tasks.images.create_download_asset_image_job(self.asset, self.batch_id)
        job_count = DownloadAssetImageJob.objects.filter(
            asset=self.asset, batch=self.batch_id
        ).count()
        self.assertEqual(job_count, 1)

    def test_create_new_job_if_previous_failed(self):
        failed_job = create_download_asset_image_job(
            asset=self.asset, batch=self.batch_id
        )
        failed_job.failed = timezone.now()
        failed_job.save()

        new_batch = uuid.uuid4()

        tasks.images.create_download_asset_image_job(self.asset, new_batch)
        job_count = DownloadAssetImageJob.objects.filter(asset=self.asset).count()
        self.assertEqual(job_count, 2)


class VerifyAssetImageTests(TestCase):
    def setUp(self):
        self.asset = create_asset()
        self.job = create_verify_asset_image_job(asset=self.asset)
        self.mock_task = mock.MagicMock()
        self.mock_task.request.id = uuid.uuid4()

    @mock.patch("importer.tasks.images.logger.info")
    @mock.patch("importer.tasks.images.create_download_asset_image_job")
    def test_no_storage_image(self, mock_create_job, mock_logger):
        # Use update to avoid validation of storage_image with invalid value
        Asset.objects.filter(id=self.asset.id).update(storage_image="")
        self.job.refresh_from_db()

        result = tasks.images.verify_asset_image(self.mock_task, self.job)
        self.assertFalse(result)
        mock_create_job.assert_called_once_with(self.asset, self.job.batch)
        mock_logger.assert_any_call(
            f"No storage image set on {self.asset} ({self.asset.id})"
        )

    @mock.patch("importer.tasks.images.logger.info")
    @mock.patch("importer.tasks.images.create_download_asset_image_job")
    @mock.patch("importer.tasks.images.ASSET_STORAGE.exists", return_value=False)
    def test_storage_image_missing(self, mock_exists, mock_create_job, mock_logger):
        result = tasks.images.verify_asset_image(self.mock_task, self.job)
        self.assertFalse(result)
        mock_create_job.assert_called_once_with(self.asset, self.job.batch)
        mock_logger.assert_any_call(
            f"Storage image for {self.asset} ({self.asset.id}) missing from storage"
        )

    @mock.patch("importer.tasks.images.logger.info")
    @mock.patch("importer.tasks.images.create_download_asset_image_job")
    @mock.patch("importer.tasks.images.ASSET_STORAGE.exists", return_value=True)
    @mock.patch("importer.tasks.images.ASSET_STORAGE.open")
    @mock.patch(
        "importer.tasks.images.Image.open",
        side_effect=Image.UnidentifiedImageError("Invalid image format"),
    )
    def test_storage_image_invalid(
        self, mock_image_open, mock_open, mock_exists, mock_create_job, mock_logger
    ):
        result = tasks.images.verify_asset_image(self.mock_task, self.job)
        self.assertFalse(result)
        mock_create_job.assert_called_once_with(self.asset, self.job.batch)
        mock_logger.assert_any_call(
            f"Storage image for {self.asset} ({self.asset.id}), "
            f"{self.asset.storage_image.name}, is corrupt. The exception "
            "raised was Type: UnidentifiedImageError, Message: Invalid image format"
        )

    @mock.patch("importer.tasks.images.logger.info")
    @mock.patch("importer.tasks.images.create_download_asset_image_job")
    @mock.patch("importer.tasks.images.ASSET_STORAGE.exists", return_value=True)
    @mock.patch("importer.tasks.images.ASSET_STORAGE.open")
    @mock.patch("importer.tasks.images.Image.open")
    def test_storage_image_verify_fail(
        self, mock_image_open, mock_open, mock_exists, mock_create_job, mock_logger
    ):
        mock_image = mock.MagicMock()
        mock_image.verify.side_effect = Image.UnidentifiedImageError(
            "Invalid image format"
        )
        mock_image_open.return_value.__enter__.return_value = mock_image

        result = tasks.images.verify_asset_image(self.mock_task, self.job)
        self.assertFalse(result)
        mock_create_job.assert_called_once_with(self.asset, self.job.batch)
        mock_logger.assert_any_call(
            f"Storage image for {self.asset} ({self.asset.id}), "
            f"{self.asset.storage_image.name}, is corrupt. The exception "
            "raised was Type: UnidentifiedImageError, Message: Invalid image format"
        )

    @mock.patch("importer.tasks.images.logger.info")
    @mock.patch("importer.tasks.images.ASSET_STORAGE.exists", return_value=True)
    @mock.patch("importer.tasks.images.ASSET_STORAGE.open")
    @mock.patch("importer.tasks.images.Image.open")
    def test_storage_image_verification_success(
        self, mock_image_open, mock_open, mock_exists, mock_logger
    ):
        mock_image = mock.MagicMock()
        mock_image.verify.return_value = None
        mock_image_open.return_value.__enter__.return_value = mock_image

        result = tasks.images.verify_asset_image(self.mock_task, self.job)
        self.assertTrue(result)
        mock_logger.assert_any_call(
            "Storage image for %s (%s), %s, verified successfully",
            self.asset,
            self.asset.id,
            self.asset.storage_image.name,
        )


class BatchDownloadAssetImagesTaskCallbackTests(TestCase):
    def setUp(self):
        self.batch_id = uuid.uuid4()
        self.concurrency = 5

    @mock.patch("importer.tasks.images.batch_download_asset_images_task.delay")
    def test_callback_triggers_next_batch(self, mock_task):
        results = [True, False, True]

        tasks.images.batch_download_asset_images_task_callback(
            results, self.batch_id, self.concurrency
        )

        mock_task.assert_called_once_with(self.batch_id, self.concurrency)

    @mock.patch("importer.tasks.images.batch_download_asset_images_task.delay")
    def test_callback_with_no_results(self, mock_task):
        results = []

        tasks.images.batch_download_asset_images_task_callback(
            results, self.batch_id, self.concurrency
        )

        mock_task.assert_called_once_with(self.batch_id, self.concurrency)

    @mock.patch("importer.tasks.images.batch_download_asset_images_task.delay")
    def test_callback_with_all_successful_results(self, mock_task):
        results = [True, True, True]

        tasks.images.batch_download_asset_images_task_callback(
            results, self.batch_id, self.concurrency
        )

        mock_task.assert_called_once_with(self.batch_id, self.concurrency)


class BatchDownloadAssetImagesTaskTests(TestCase):
    def setUp(self):
        self.batch_id = uuid.uuid4()
        self.concurrency = 3
        asset1 = create_asset()
        asset2 = create_asset(item=asset1.item, slug="test-asset-2")
        asset3 = create_asset(item=asset1.item, slug="test-asset-3")
        self.job1 = create_download_asset_image_job(batch=self.batch_id, asset=asset1)
        self.job2 = create_download_asset_image_job(batch=self.batch_id, asset=asset2)
        self.job3 = create_download_asset_image_job(batch=self.batch_id, asset=asset3)

    @mock.patch("importer.tasks.images.logger.info")
    @mock.patch("importer.tasks.images.chord")
    @mock.patch("importer.tasks.images.download_asset_image_task.s")
    def test_jobs_remaining(self, mock_task_s, mock_chord, mock_logger):
        tasks.images.batch_download_asset_images_task(self.batch_id, self.concurrency)
        self.assertEqual(mock_task_s.call_count, 3)
        mock_chord.assert_called()
        mock_logger.assert_any_call(
            "Processing next %s DownloadAssetImageJobs for batch %s",
            self.concurrency,
            self.batch_id,
        )

    @mock.patch("importer.tasks.images.logger.info")
    def test_no_jobs_remaining(self, mock_logger):
        DownloadAssetImageJob.objects.all().delete()
        tasks.images.batch_download_asset_images_task(self.batch_id, self.concurrency)
        mock_logger.assert_any_call(
            "No DownloadAssetImageJobs found for batch %s", self.batch_id
        )


class DownloadAssetImageTaskTests(TestCase):
    def setUp(self):
        self.asset = create_asset()
        self.batch_id = uuid.uuid4()

    @mock.patch("importer.tasks.images.logger.exception")
    def test_asset_not_found(self, mock_logger):
        with self.assertRaises(Asset.DoesNotExist):
            tasks.images.download_asset_image_task(999)
        mock_logger.assert_called()

    @mock.patch("importer.tasks.images.logger.exception")
    def test_download_job_not_found(self, mock_logger):
        with self.assertRaises(DownloadAssetImageJob.DoesNotExist):
            tasks.images.download_asset_image_task(
                self.asset.pk, self.batch_id, create_job=False
            )
        mock_logger.assert_called()

    @mock.patch("importer.tasks.images.download_asset")
    def test_download_asset_image_task_success(self, mock_download):
        create_download_asset_image_job(asset=self.asset, batch=self.batch_id)
        mock_download.return_value = "Download successful"

        result = tasks.images.download_asset_image_task(self.asset.pk, self.batch_id)
        self.assertEqual(result, "Download successful")

    @mock.patch("importer.tasks.images.download_asset")
    def test_create_download_asset_image_job(self, mock_download):
        mock_download.return_value = "Download successful"
        result = tasks.images.download_asset_image_task(
            self.asset.pk, self.batch_id, create_job=True
        )
        self.assertEqual(result, "Download successful")
        self.assertTrue(
            DownloadAssetImageJob.objects.filter(
                asset=self.asset, batch=self.batch_id
            ).exists()
        )

    @mock.patch("importer.tasks.images.download_asset")
    def test_http_error_retries(self, mock_download):
        mock_download.side_effect = requests.exceptions.HTTPError("HTTP Error Occurred")
        with self.assertRaises(requests.exceptions.HTTPError):
            tasks.images.download_asset_image_task(
                self.asset.pk, self.batch_id, create_job=True
            )
