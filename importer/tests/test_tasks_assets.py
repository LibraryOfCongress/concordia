import uuid
from unittest import mock

import requests
from django.core.cache import caches
from django.db.models import Max
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import UnidentifiedImageError

from concordia.models import Asset
from concordia.tests.utils import create_asset
from configuration.models import Configuration
from importer import exceptions, tasks
from importer.models import (
    DownloadAssetImageJob,
    ImportItemAsset,
    TaskStatusModel,
    VerifyAssetImageJob,
)

from .utils import (
    create_download_asset_image_job,
    create_import_asset,
    create_verify_asset_image_job,
)


class RedownloadImageTaskTests(TestCase):
    @mock.patch("importer.tasks.images.download_asset")
    def test_redownload_image_task(self, mock_download):
        tasks.images.redownload_image_task(create_asset().pk)
        self.assertTrue(mock_download.called)


class AssetImportTests(TestCase):
    def setUp(self):
        for cache in caches.all():
            cache.clear()

        self.import_asset = create_import_asset(url="http://example.com")
        self.asset = self.import_asset.asset
        self.job = create_download_asset_image_job(asset=self.asset)

        # It's difficult/impossible to cleanly mock a decorator due to the way
        # they're applied when the decorated object/function is evaluated on
        # import, so we unfortunately have to handle the update_task_status
        # decorator, so we need a mock object that can pass for a Celery task
        # object so update_task_status doesn't error during the test
        self.task_mock = mock.MagicMock()
        self.task_mock.request.id = "f81d4fae-7dec-11d0-a765-00a0c91e6bf6"

        self.get_return_value = [b"chunk1", b"chunk2"]

        self.valid_hash = "097c42989a9e5d9dcced7b35ec4b0486"
        self.invalid_hash = "bad-hash"

        self.filename = self.asset.get_asset_image_filename()

        self.head_object_mock = mock.MagicMock()
        self.s3_client_mock = mock.MagicMock()
        self.s3_client_mock.head_object = self.head_object_mock

    def tearDown(self):
        for cache in caches.all():
            cache.clear()

    def test_get_asset_urls_from_item_resources_empty(self):
        self.assertEqual(tasks.items.get_asset_urls_from_item_resources([]), ([], ""))

    def test_get_asset_urls_from_item_resources_url_only(self):
        results = tasks.items.get_asset_urls_from_item_resources(
            [{"url": "http://example.com"}]
        )
        self.assertEqual(results, ([], "http://example.com"))

    def test_get_asset_urls_from_item_resources_valid(self):
        results = tasks.items.get_asset_urls_from_item_resources(
            [
                {
                    "url": "http://example.com",
                    "files": [
                        [
                            {
                                "url": "http://example.com/1.jpg",
                                "height": 1,
                                "width": 1,
                                "mimetype": "image/jpeg",
                            },
                            {"url": "http://example.com/2.jpg"},
                            {
                                "url": "http://example.com/3.jpg",
                                "height": 2,
                                "width": 2,
                                "mimetype": "image/jpeg",
                            },
                            {
                                "url": "http://example.com/4.jpg",
                                "height": 100,
                                "width": 100,
                                "mimetype": "image/gif",
                            },
                        ]
                    ],
                }
            ]
        )
        self.assertEqual(results, (["http://example.com/3.jpg"], "http://example.com"))

    def test_get_asset_urls_from_item_resource_no_valid(self):
        results = tasks.items.get_asset_urls_from_item_resources(
            [
                {
                    "url": "http://example.com",
                    "files": [
                        [
                            {
                                "url": "http://example.com/1.jpg",
                                "height": 1,
                                "width": 1,
                                "mimetype": "file/pdf",
                            },
                            {"url": "http://example.com/2.jpg"},
                            {
                                "url": "http://example.com/3.jpg",
                                "height": 2,
                                "width": 2,
                                "mimetype": "video/mov",
                            },
                            {
                                "url": "http://example.com/4.jpg",
                                "height": 100,
                                "width": 100,
                                "mimetype": "image/tiff",
                            },
                        ]
                    ],
                }
            ]
        )
        self.assertEqual(results, ([], "http://example.com"))

    def test_get_asset_urls_from_item_resource_no_jpgs(self):
        results = tasks.items.get_asset_urls_from_item_resources(
            [
                {
                    "url": "http://example.com",
                    "files": [
                        [
                            {
                                "url": "http://example.com/1.jpg",
                                "height": 1,
                                "width": 1,
                                "mimetype": "file/pdf",
                            },
                            {"url": "http://example.com/2.jpg"},
                            {
                                "url": "http://example.com/3.gif",
                                "height": 2,
                                "width": 2,
                                "mimetype": "image/gif",
                            },
                            {
                                "url": "http://example.com/4.gif",
                                "height": 100,
                                "width": 100,
                                "mimetype": "image/gif",
                            },
                        ]
                    ],
                }
            ]
        )
        self.assertEqual(results, (["http://example.com/4.gif"], "http://example.com"))

    def test_download_asset_task(self):
        with mock.patch("importer.tasks.assets.download_asset") as task_mock:
            tasks.assets.download_asset_task(self.import_asset.pk)
            self.assertTrue(task_mock.called)
            task, called_import_asset = task_mock.call_args.args
            self.assertTrue(called_import_asset, self.import_asset)

            # Test sending a bad pk
            task_mock.reset_mock()
            max_pk = ImportItemAsset.objects.aggregate(Max("pk"))["pk__max"]
            with self.assertRaises(ImportItemAsset.DoesNotExist):
                tasks.assets.download_asset_task(max_pk + 1)
            self.assertFalse(task_mock.called)

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            "assets": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        },
        AWS_STORAGE_BUCKET_NAME="test-bucket",
    )
    def test_download_asset_valid(self):
        with (
            mock.patch("importer.tasks.assets.requests.get") as get_mock,
            mock.patch("importer.tasks.assets.boto3.client") as boto_mock,
            mock.patch("importer.tasks.assets.flag_enabled") as flag_mock,
        ):
            get_mock.return_value.iter_content.return_value = self.get_return_value
            boto_mock.return_value = self.s3_client_mock
            flag_mock.return_value = True
            self.head_object_mock.return_value = {"ETag": f'"{self.valid_hash}"'}

            tasks.assets.download_asset(self.task_mock, self.import_asset)

            self.assertEqual(get_mock.call_args[0], ("http://example.com",))
            self.assertTrue(get_mock.call_args[1]["stream"])

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            "assets": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        },
        AWS_STORAGE_BUCKET_NAME="test-bucket",
    )
    def test_download_asset_valid_checksum_fail(self):
        with (
            mock.patch("importer.tasks.assets.requests.get") as get_mock,
            mock.patch("importer.tasks.assets.boto3.client") as boto_mock,
            mock.patch("importer.tasks.assets.flag_enabled") as flag_mock,
        ):
            get_mock.return_value.iter_content.return_value = self.get_return_value
            boto_mock.return_value = self.s3_client_mock
            flag_mock.return_value = True
            self.head_object_mock.return_value = {"ETag": f'"{self.invalid_hash}"'}

            with self.assertRaises(Exception) as assertion:
                tasks.assets.download_asset(self.task_mock, self.import_asset)

            self.assertEqual(
                str(assertion.exception),
                f"ETag {self.invalid_hash} for {self.filename} did not match "
                f"calculated md5 hash {self.valid_hash}",
            )

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            "assets": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        },
        AWS_STORAGE_BUCKET_NAME="test-bucket",
    )
    def test_download_asset_valid_checksum_fail_without_flag(self):
        with (
            mock.patch("importer.tasks.assets.requests.get") as get_mock,
            mock.patch("importer.tasks.assets.boto3.client") as boto_mock,
            self.assertLogs("importer.tasks", level="WARN") as log,
        ):
            get_mock.return_value.iter_content.return_value = self.get_return_value
            boto_mock.return_value = self.s3_client_mock
            self.head_object_mock.return_value = {"ETag": f'"{self.invalid_hash}"'}

            tasks.assets.download_asset(self.task_mock, self.import_asset)
            self.assertEqual(
                log.output[0],
                f"WARNING:importer.tasks.assets:ETag ({self.invalid_hash}) for "
                f"{self.filename} did not match calculated md5 hash "
                f"({self.valid_hash}) but the IMPORT_IMAGE_CHECKSUM flag is disabled",
            )

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            "assets": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        },
        AWS_STORAGE_BUCKET_NAME="test-bucket",
    )
    def test_download_asset_invalid(self):
        with (
            mock.patch("importer.tasks.assets.requests.get") as get_mock,
            self.assertLogs("importer.tasks", level="ERROR") as log,
        ):
            get_mock.return_value.raise_for_status.side_effect = AttributeError
            with self.assertRaises(exceptions.ImageImportFailure):
                tasks.assets.download_asset(self.task_mock, self.import_asset)
            # Since the logging includes a stacktrace, we just check the
            # beginning of the log entry with assertIn
            self.assertIn(
                "ERROR:importer.tasks.assets:"
                "Unable to download http://example.com to "
                "test-campaign/test-project/testitem.0123456789/1.jpg",
                log.output[0],
            )

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            "assets": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        },
        AWS_STORAGE_BUCKET_NAME="test-bucket",
    )
    def test_download_asset_retry_success(self):
        import_asset = self.import_asset
        import_asset.failed = timezone.now()
        import_asset.completed = None
        import_asset.failure_reason = TaskStatusModel.FailureReason.IMAGE
        import_asset.status = "Test failed status"
        import_asset.retry_count = 0
        import_asset.failure_history = []
        import_asset.save()

        with mock.patch(
            "importer.models.tasks.assets.download_asset_task"
        ) as task_mock:
            response = import_asset.retry_if_possible()

            self.assertNotEqual(response, False)
            self.assertTrue(task_mock.apply_async.called)
            self.assertEqual(len(import_asset.failure_history), 1)
            self.assertEqual(import_asset.failed, None)
            self.assertEqual(import_asset.retry_count, 1)
            self.assertEqual(import_asset.failure_reason, "")

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            "assets": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        },
        AWS_STORAGE_BUCKET_NAME="test-bucket",
    )
    def test_download_asset_retry_maximum_exceeded(self):
        try:
            config = Configuration.objects.get(key="asset_image_import_max_retries")
            config.value = "1"
            config.data_type = Configuration.DataType.NUMBER
            config.save()
        except Configuration.DoesNotExist:
            Configuration.objects.create(
                key="asset_image_import_max_retries",
                value="1",
                data_type=Configuration.DataType.NUMBER,
            )

        import_asset = self.import_asset
        import_asset.failed = timezone.now()
        import_asset.completed = None
        import_asset.failure_reason = TaskStatusModel.FailureReason.IMAGE
        import_asset.status = "Test failed status"
        import_asset.retry_count = 1
        import_asset.failure_history = []
        import_asset.save()

        with mock.patch(
            "importer.models.tasks.assets.download_asset_task"
        ) as task_mock:
            response = import_asset.retry_if_possible()

            self.assertFalse(response)
            self.assertFalse(task_mock.apply_async.called)
            self.assertEqual(len(import_asset.failure_history), 1)
            self.assertNotEqual(import_asset.failed, None)
            self.assertEqual(
                import_asset.status,
                "Maximum number of retries reached while retrying image download "
                "for asset. The failure reason before retrying was Image and the "
                "status was Test failed status",
            )
            self.assertEqual(import_asset.retry_count, 1)
            self.assertEqual(
                import_asset.failure_reason, TaskStatusModel.FailureReason.RETRIES
            )

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            "assets": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        },
        AWS_STORAGE_BUCKET_NAME="test-bucket",
    )
    def test_download_asset_retry_cant_reset(self):
        import_asset = self.import_asset
        import_asset.completed = None
        import_asset.failure_reason = TaskStatusModel.FailureReason.IMAGE
        import_asset.status = "Test failed status"
        import_asset.retry_count = 0
        import_asset.failure_history = []
        import_asset.save()

        with mock.patch(
            "importer.models.tasks.assets.download_asset_task"
        ) as task_mock:
            response = import_asset.retry_if_possible()

            self.assertFalse(response)
            self.assertFalse(task_mock.apply_async.called)
            self.assertNotEqual(import_asset.status, "Test failed status")
            self.assertEqual(len(import_asset.failure_history), 0)
            self.assertEqual(import_asset.failed, None)
            self.assertEqual(import_asset.retry_count, 0)
            self.assertEqual(
                import_asset.failure_reason, TaskStatusModel.FailureReason.IMAGE
            )

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            "assets": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        },
        AWS_STORAGE_BUCKET_NAME="test-bucket",
    )
    def test_download_asset_retry_invalid_failure_reason(self):
        import_asset = self.import_asset
        import_asset.failed = timezone.now()
        import_asset.completed = None
        import_asset.failure_reason = ""
        import_asset.status = "Test failed status"
        import_asset.retry_count = 0
        import_asset.failure_history = []
        import_asset.save()

        with mock.patch(
            "importer.models.tasks.assets.download_asset_task"
        ) as task_mock:
            response = import_asset.retry_if_possible()

            self.assertFalse(response)
            self.assertFalse(task_mock.apply_async.called)
            self.assertEqual(import_asset.status, "Test failed status")
            self.assertEqual(len(import_asset.failure_history), 0)
            self.assertNotEqual(import_asset.failed, None)
            self.assertEqual(import_asset.retry_count, 0)
            self.assertEqual(import_asset.failure_reason, "")

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            "assets": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        },
        AWS_STORAGE_BUCKET_NAME="test-bucket",
    )
    def test_download_asset_manual_retry_success(self):
        # This mimics an admin manually retrying the task, rather than
        # the automatic retry system (such as through an admin action).
        # We want to be sure the failure information is correctly reset.
        import_asset = self.import_asset
        import_asset.failed = timezone.now()
        import_asset.completed = None
        import_asset.failure_reason = ""
        import_asset.status = "Test failed status"
        import_asset.retry_count = 0
        import_asset.failure_history = []
        import_asset.save()

        with mock.patch(
            "importer.models.tasks.assets.download_and_store_asset_image"
        ) as download_mock:
            download_mock.return_value = "image.jpg"

            tasks.assets.download_asset_task.delay(import_asset.pk)
            import_asset.refresh_from_db()
            self.assertTrue(download_mock.called)
            self.assertEqual(import_asset.status, "Completed")
            self.assertEqual(len(import_asset.failure_history), 0)
            self.assertEqual(import_asset.failed, None)
            self.assertEqual(import_asset.retry_count, 0)
            self.assertEqual(import_asset.failure_reason, "")

    @mock.patch("importer.tasks.assets.download_and_store_asset_image")
    @mock.patch("importer.tasks.assets.logger.info")
    def test_download_url_from_asset(self, mock_logger, mock_download):
        self.asset.download_url = "https://example.com/image.png"
        self.asset.save()
        self.job.refresh_from_db()

        mock_download.return_value = "stored_image.png"

        tasks.assets.download_asset(self.task_mock, self.job)

        mock_download.assert_called_once_with(self.asset.download_url, mock.ANY)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.storage_image, "stored_image.png")
        mock_logger.assert_any_call(
            "Download and storage of asset image %s complete. Setting storage_image "
            "on asset %s (%s)",
            "stored_image.png",
            self.asset,
            self.asset.id,
        )

    @mock.patch("importer.tasks.assets.download_and_store_asset_image")
    @mock.patch("importer.tasks.assets.logger.info")
    def test_valid_file_extension(self, mock_logger, mock_download):
        self.asset.download_url = "https://example.com/image.png"
        self.asset.save()
        self.job.refresh_from_db()

        mock_download.return_value = "stored_image.png"
        tasks.assets.download_asset(self.task_mock, self.job)

        asset_image_filename = self.asset.get_asset_image_filename("png")
        mock_download.assert_called_once_with(
            self.asset.download_url, asset_image_filename
        )

        self.asset.refresh_from_db()
        self.assertEqual(self.asset.storage_image, "stored_image.png")
        mock_logger.assert_any_call(
            "Download and storage of asset image %s complete. Setting storage_image "
            "on asset %s (%s)",
            "stored_image.png",
            self.asset,
            self.asset.id,
        )


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
        # Use update in order to avoid the validation of storage_image, since this is
        # an invalid value, but we have to account for it
        Asset.objects.filter(id=self.asset.id).update(storage_image="")
        # We need to update the job from the database to get rid of the cached asset
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
        side_effect=UnidentifiedImageError("Invalid image format"),
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
        mock_image.verify.side_effect = UnidentifiedImageError("Invalid image format")
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
