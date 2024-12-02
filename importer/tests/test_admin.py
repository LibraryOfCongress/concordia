from unittest import mock

from django.contrib import messages
from django.test import RequestFactory, TestCase

from importer.admin import retry_download_task
from importer.models import ImportItemAsset

from .utils import create_import_asset


@mock.patch("importer.admin.download_asset_task.delay", autospec=True)
@mock.patch("importer.admin.messages.add_message", autospec=True)
class ActionTests(TestCase):
    def test_retry_download_task(self, messages_mock, task_mock):
        import_asset1 = create_import_asset(0)
        import_assets = [import_asset1] + [
            create_import_asset(i, import_item=import_asset1.import_item)
            for i in range(1, 10)
        ]
        import_asset_count = len(import_assets)
        import_asset_args = [(import_asset.pk,) for import_asset in import_assets]
        modeladmin_mock = mock.MagicMock()
        request = RequestFactory().get("/")

        retry_download_task(modeladmin_mock, request, ImportItemAsset.objects.all())
        args_list = [arg for arg, kwargs in task_mock.call_args_list]

        self.assertEqual(task_mock.call_count, import_asset_count)
        self.assertEqual(args_list, import_asset_args)
        self.assertEqual(messages_mock.call_count, 1)
        self.assertEqual(
            messages_mock.call_args.args,
            (request, messages.INFO, f"Queued {import_asset_count} tasks"),
        )
