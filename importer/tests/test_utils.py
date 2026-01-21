import uuid
from unittest import mock

from django.test import TestCase

from concordia.tests.utils import create_asset
from importer.models import VerifyAssetImageJob
from importer.utils import create_verify_asset_image_job_batch
from importer.utils.excel import clean_cell_value, slurp_excel


class CreateVerifyAssetImageJobBatchTests(TestCase):
    def setUp(self):
        self.batch_id = uuid.uuid4()
        self.asset = create_asset()
        self.assets = [self.asset] + [
            create_asset(item=self.asset.item, slug=f"test-asset-{i}")
            for i in range(1, 5)
        ]
        self.asset_pks = [asset.pk for asset in self.assets]

    @mock.patch("importer.tasks.images.batch_verify_asset_images_task.delay")
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

    @mock.patch("importer.tasks.images.batch_verify_asset_images_task.delay")
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

    @mock.patch("importer.tasks.images.batch_verify_asset_images_task.delay")
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


class ExcelUtilsTests(TestCase):
    class _Cell:
        def __init__(self, data_type, value):
            self.data_type = data_type
            self.value = value

    class _Worksheet:
        def __init__(self, rows):
            # rows is a list of tuples of _Cell
            self._rows = rows

        @property
        def rows(self):
            return iter(self._rows)

    class _Workbook:
        def __init__(self, worksheets):
            self.worksheets = worksheets

    @mock.patch("importer.utils.excel.load_workbook")
    def test_slurp_excel_single_worksheet_single_row(self, load_mock):
        ws_rows = [
            (
                type(self)._Cell("s", " Name "),
                type(self)._Cell("s", "Age"),
            ),
            (
                type(self)._Cell("s", " Alice "),
                type(self)._Cell("n", 30),
            ),
        ]
        wb = type(self)._Workbook([type(self)._Worksheet(ws_rows)])
        load_mock.return_value = wb

        out = slurp_excel("ignored.xlsx")

        self.assertEqual(out, [{"Name": "Alice", "Age": 30}])

    @mock.patch("importer.utils.excel.load_workbook")
    def test_slurp_excel_multiple_worksheets_multiple_rows(self, load_mock):
        ws1_rows = [
            (type(self)._Cell("s", "H1"),),
            (type(self)._Cell("s", "v1"),),
            (type(self)._Cell("s", " v2 "),),
        ]
        ws2_rows = [
            (
                type(self)._Cell("s", " H2 "),
                type(self)._Cell("s", "H3"),
            ),
            (
                type(self)._Cell("n", 1),
                type(self)._Cell("s", "  x "),
            ),
        ]
        wb = type(self)._Workbook(
            [type(self)._Worksheet(ws1_rows), type(self)._Worksheet(ws2_rows)]
        )
        load_mock.return_value = wb

        out = slurp_excel("ignored.xlsx")

        # Order is by worksheet, then row order within each worksheet.
        self.assertEqual(
            out,
            [
                {"H1": "v1"},
                {"H1": "v2"},
                {"H2": 1, "H3": "x"},
            ],
        )

    def test_clean_cell_value_trims_strings(self):
        c = type(self)._Cell("s", "  padded  ")
        self.assertEqual(clean_cell_value(c), "padded")

    def test_clean_cell_value_passthrough_non_strings(self):
        c_num = type(self)._Cell("n", 42)
        c_bool = type(self)._Cell("b", True)
        self.assertEqual(clean_cell_value(c_num), 42)
        self.assertTrue(clean_cell_value(c_bool))
