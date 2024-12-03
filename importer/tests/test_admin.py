from unittest import mock

from django.contrib import messages
from django.test import RequestFactory, TestCase

from concordia.models import Campaign
from concordia.tests.utils import create_campaign
from importer.admin import (
    ImportCampaignListFilter,
    TaskStatusModelAdmin,
    retry_download_task,
)
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


class ImportCampaignListFilterTest(TestCase):
    def test_lookups(self):
        class TestImportCampaignListFilter(ImportCampaignListFilter):
            # We need a subclass because ImportCampaignListFilter itself
            # isn't meant to be used directly, and can't be due
            # to not having a parameter_name configured
            parameter_name = "campaign"

        campaigns = [create_campaign(slug=f"test-campaign-{i}") for i in range(5)]
        campaigns += [
            create_campaign(
                slug="test-campaign-completed", status=Campaign.Status.COMPLETED
            )
        ]
        retired_campaign = create_campaign(
            slug="test-campaign-retired",
            title="Retired Campaign",
            status=Campaign.Status.RETIRED,
        )

        philter = TestImportCampaignListFilter(
            None, {}, mock.MagicMock(), mock.MagicMock()
        )
        values_list = philter.lookups(mock.MagicMock(), mock.MagicMock())

        self.assertEqual(len(values_list), len(campaigns))
        for idx, title in values_list:
            self.assertNotEqual(idx, retired_campaign.id)
            self.assertNotIn("Retired", title)


@mock.patch("importer.admin.naturaltime")
class TaskStatusModelAdminTest(TestCase):
    def test_generate_natural_timestamp_display_property(self, naturaltime_mock):
        inner = TaskStatusModelAdmin.generate_natural_timestamp_display_property(
            "test_field"
        )

        obj = mock.MagicMock()
        value = inner(obj)
        self.assertTrue(naturaltime_mock.called)

        naturaltime_mock.reset_mock()
        obj = mock.MagicMock(spec=["test_field"])
        obj.test_field = None
        value = inner(obj)
        self.assertEqual(value, None)
        self.assertFalse(naturaltime_mock.called)

        naturaltime_mock.reset_mock()
        # Passing an empty list to spec means there are no
        # attributes on the mock, so accessing any attribute
        # will raise an AttributeError
        obj = mock.MagicMock(spec=[])
        value = inner(obj)
        self.assertEqual(value, None)
        self.assertFalse(naturaltime_mock.called)
