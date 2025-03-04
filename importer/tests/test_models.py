from django.test import TestCase
from django.utils import timezone

from concordia.tests.utils import CreateTestUsers, create_project
from importer.models import TaskStatusModel

from .utils import create_import_asset, create_import_item, create_import_job


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
