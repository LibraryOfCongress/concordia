import uuid

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from concordia.tests.utils import CreateTestUsers, create_asset, create_project
from importer.models import TaskStatusModel

from .utils import (
    create_download_asset_image_job,
    create_import_asset,
    create_import_item,
    create_import_job,
    create_verify_asset_image_job,
)


class ImportJobTests(TestCase, CreateTestUsers):
    def test_str(self):
        user = self.create_test_user()
        project = create_project()
        url = "http://example.com"

        job = create_import_job(project=project)

        self.assertEqual(
            str(job), f"ImportJob(created_by=None, project={project.title}, url=)"
        )

        job.created_by = user
        job.url = url

        self.assertEqual(
            str(job),
            f"ImportJob(created_by={user.username}, "
            f"project={project.title}, url={url})",
        )

    def test_retry_if_possible(self):
        # This method is just a placeholder for this model,
        # so we're just testing to make sure it doesn't error
        # and returns False, since any other value will cause issues
        job = create_import_job()

        self.assertFalse(job.retry_if_possible())

    def test_update_failure_history(self):
        job = create_import_job()
        job.failed = timezone.now()
        job.failure_reason = TaskStatusModel.FailureReason.IMAGE
        job.status = "Test failure status"
        job.failure_history = []
        job.save()
        job.update_failure_history()

        failure_history = job.failure_history
        self.assertEqual(len(failure_history), 1)
        self.assertNotEqual(failure_history[0]["failed"], "")
        self.assertEqual(
            failure_history[0]["failure_reason"], TaskStatusModel.FailureReason.IMAGE
        )
        self.assertEqual(failure_history[0]["status"], "Test failure status")


class ImportItemTests(TestCase, CreateTestUsers):
    def test_str(self):
        job = create_import_job()
        url = "http://example.com"

        item = create_import_item(import_job=job)

        self.assertEqual(str(item), f"ImportItem(job={job}, url=)")

        item.url = url

        self.assertEqual(str(item), f"ImportItem(job={job}, url={url})")

    def test_retry_if_possible(self):
        # This method is just a placeholder for this model,
        # so we're just testing to make sure it doesn't error
        # and returns False, since any other value will cause issues
        item = create_import_item()

        self.assertFalse(item.retry_if_possible())


class ImportItemAssetTests(TestCase, CreateTestUsers):
    def test_str(self):
        item = create_import_item()
        url = "http://example.com"

        asset = create_import_asset(import_item=item)

        self.assertEqual(str(asset), f"ImportItemAsset(import_item={item}, url=)")

        asset.url = url

        self.assertEqual(str(asset), f"ImportItemAsset(import_item={item}, url={url})")


class VerifyAssetImageJobTests(TestCase):
    def setUp(self):
        self.asset = create_asset()
        self.batch_id = uuid.uuid4()
        self.job = create_verify_asset_image_job(asset=self.asset, batch=self.batch_id)

    def test_str_representation(self):
        self.assertEqual(str(self.job), f"VerifyAssetImageJob for {self.asset}")

    def test_batch_admin_url(self):
        expected_url = (
            reverse("admin:importer_verifyassetimagejob_changelist")
            + f"?batch={self.batch_id}"
        )
        self.assertEqual(self.job.batch_admin_url, expected_url)

    def test_get_batch_admin_url(self):
        expected_url = (
            reverse("admin:importer_verifyassetimagejob_changelist")
            + f"?batch={self.batch_id}"
        )
        url = self.job.__class__.get_batch_admin_url(self.batch_id)
        self.assertEqual(url, expected_url)

    def test_get_batch_admin_url_error(self):
        with self.assertRaises(ValueError):
            self.job.__class__.get_batch_admin_url("")

    def test_update_failure_history(self):
        self.job.failed = timezone.now()
        self.job.failure_reason = "Image"
        self.job.status = "Failed due to image error"
        self.job.update_failure_history()
        self.assertEqual(len(self.job.failure_history), 1)
        self.assertEqual(self.job.failure_history[0]["failure_reason"], "Image")

    def test_update_status(self):
        self.job.update_status("Processing")
        self.assertEqual(self.job.status, "Processing")
        self.assertEqual(len(self.job.status_history), 1)
        self.assertEqual(self.job.status_history[0]["status"], "")

    def test_reset_for_retry(self):
        self.job.failed = timezone.now()
        self.assertTrue(self.job.reset_for_retry())
        self.assertIsNone(self.job.failed)
        self.assertEqual(self.job.retry_count, 1)

    def test_reset_for_retry_when_not_failed(self):
        self.assertFalse(self.job.reset_for_retry())
        self.assertEqual(
            self.job.status,
            "Task was not marked as failed, so it will not be reset for retrying.",
        )


class DownloadAssetImageJobTests(TestCase):
    def setUp(self):
        self.asset = create_asset()
        self.batch_id = uuid.uuid4()
        self.job = create_download_asset_image_job(
            asset=self.asset, batch=self.batch_id
        )

    def test_str_representation(self):
        self.assertEqual(str(self.job), f"DownloadAssetImageJob for {self.asset}")

    def test_batch_admin_url(self):
        expected_url = (
            reverse("admin:importer_downloadassetimagejob_changelist")
            + f"?batch={self.batch_id}"
        )
        self.assertEqual(self.job.batch_admin_url, expected_url)

    def test_get_batch_admin_url(self):
        expected_url = (
            reverse("admin:importer_downloadassetimagejob_changelist")
            + f"?batch={self.batch_id}"
        )
        url = self.job.__class__.get_batch_admin_url(self.batch_id)
        self.assertEqual(url, expected_url)

    def test_get_batch_admin_url_error(self):
        with self.assertRaises(ValueError):
            self.job.__class__.get_batch_admin_url("")

    def test_update_failure_history(self):
        self.job.failed = timezone.now()
        self.job.failure_reason = "Image"
        self.job.status = "Failed due to image error"
        self.job.update_failure_history()
        self.assertEqual(len(self.job.failure_history), 1)
        self.assertEqual(self.job.failure_history[0]["failure_reason"], "Image")

    def test_update_status(self):
        self.job.update_status("Processing")
        self.assertEqual(self.job.status, "Processing")
        self.assertEqual(len(self.job.status_history), 1)
        self.assertEqual(self.job.status_history[0]["status"], "")

    def test_reset_for_retry(self):
        self.job.failed = timezone.now()
        self.assertTrue(self.job.reset_for_retry())
        self.assertIsNone(self.job.failed)
        self.assertEqual(self.job.retry_count, 1)

    def test_reset_for_retry_when_not_failed(self):
        self.assertFalse(self.job.reset_for_retry())
        self.assertEqual(
            self.job.status,
            "Task was not marked as failed, so it will not be reset for retrying.",
        )
