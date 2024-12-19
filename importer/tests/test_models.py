from django.test import TestCase

from concordia.tests.utils import CreateTestUsers, create_project

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


class ImportItemTests(TestCase, CreateTestUsers):
    def test_str(self):
        job = create_import_job()
        url = "http://example.com"

        item = create_import_item(import_job=job)

        self.assertEqual(str(item), f"ImportItem(job={job}, url=)")

        item.url = url

        self.assertEqual(str(item), f"ImportItem(job={job}, url={url})")


class ImportItemAssetTests(TestCase, CreateTestUsers):
    def test_str(self):
        item = create_import_item()
        url = "http://example.com"

        asset = create_import_asset(import_item=item)

        self.assertEqual(str(asset), f"ImportItemAsset(import_item={item}, url=)")

        asset.url = url

        self.assertEqual(str(asset), f"ImportItemAsset(import_item={item}, url={url})")
