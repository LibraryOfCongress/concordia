import json
import tempfile
from http import HTTPStatus
from unittest import mock

from django.test import RequestFactory, TestCase
from django.urls import reverse

from concordia.admin.views import SerializedObjectView
from concordia.tests.utils import CreateTestUsers, create_asset, create_card


@mock.patch("importer.utils.excel.load_workbook", autospec=True)
@mock.patch("concordia.admin.views.redownload_image_task.delay", autospec=True)
class TestRedownloadImagesView(CreateTestUsers, TestCase):
    def setUp(self):
        self.login_user(is_staff=True, is_superuser=True)
        self.url = reverse("admin:redownload-images")
        self.asset = create_asset(download_url="http://example.com/1234.jpg")
        self.asset2 = create_asset(
            slug="asset-2",
            item=self.asset.item,
            download_url="http://example.com/5678.jpg",
        )
        self.asset3 = create_asset(
            slug="asset-3",
            item=self.asset.item,
            download_url="http://example.com/9012.jpg",
        )

    def test_get(self, task_mock, excel_mock):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(task_mock.called)
        self.assertFalse(excel_mock.called)
        with self.assertRaises(KeyError):
            response.context["assets_to_download"]

    def test_post_no_file(self, task_mock, excel_mock):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"].errors,
            {"spreadsheet_file": ["This field is required."]},
        )
        self.assertFalse(task_mock.called)
        self.assertFalse(excel_mock.called)
        with self.assertRaises(KeyError):
            response.context["assets_to_download"]

    def test_post_empty_spreadsheet(self, task_mock, excel_mock):
        with tempfile.NamedTemporaryFile() as spreadsheet:
            spreadsheet.write(b"test")
            spreadsheet.seek(0)
            data = {
                "spreadsheet_file": spreadsheet,
            }

            response = self.client.post(self.url, data)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(excel_mock.called)
            self.assertFalse(task_mock.called)
            self.assertEqual(response.context["assets_to_download"], [])

    def test_post_invalid_rows(self, task_mock, excel_mock):
        with tempfile.NamedTemporaryFile() as spreadsheet:
            spreadsheet.write(b"test")
            spreadsheet.seek(0)
            data = {
                "spreadsheet_file": spreadsheet,
            }

            # Various types of invalid rows
            rows = [
                [
                    mock.MagicMock(data_type="s", value="download_url"),
                    mock.MagicMock(data_type="s", value="real_file_url"),
                ],
                # No value for download_url
                [
                    mock.MagicMock(data_type="s", value=""),
                    mock.MagicMock(data_type="i", value="1234"),
                ],
                # No value for any cell
                [
                    mock.MagicMock(data_type="s", value=""),
                    mock.MagicMock(data_type="i", value=""),
                ],
                # download_url that doesn't start with http
                [
                    mock.MagicMock(data_type="s", value="example.com"),
                    mock.MagicMock(data_type="i", value=""),
                ],
                # download_url that doesn't exist on an asset
                [
                    mock.MagicMock(data_type="s", value="http://example.com"),
                    mock.MagicMock(data_type="i", value=""),
                ],
            ]
            worksheet = mock.MagicMock(rows=iter(rows))
            excel_mock.return_value = mock.MagicMock()
            excel_mock.return_value.worksheets = [worksheet]

            response = self.client.post(self.url, data)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(excel_mock.called)
            self.assertFalse(task_mock.called)
            self.assertEqual(response.context["assets_to_download"], [])

    def test_post_valid(self, task_mock, excel_mock):
        with tempfile.NamedTemporaryFile() as spreadsheet:
            spreadsheet.write(b"test")
            spreadsheet.seek(0)
            data = {
                "spreadsheet_file": spreadsheet,
            }

            rows = [
                [
                    mock.MagicMock(data_type="s", value="download_url"),
                    mock.MagicMock(data_type="s", value="real_file_url"),
                ],
                [
                    mock.MagicMock(data_type="s", value=self.asset.download_url),
                    mock.MagicMock(data_type="s", value=self.asset2.download_url),
                ],
                [
                    mock.MagicMock(data_type="s", value=self.asset3.download_url),
                    mock.MagicMock(data_type="s", value=""),
                ],
            ]
            worksheet = mock.MagicMock(rows=iter(rows))
            excel_mock.return_value = mock.MagicMock()
            excel_mock.return_value.worksheets = [worksheet]

            response = self.client.post(self.url, data)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(excel_mock.called)
            self.assertTrue(task_mock.called)
            self.assertEqual(
                response.context["assets_to_download"], [self.asset, self.asset3]
            )
            asset = response.context["assets_to_download"][0]
            self.assertEqual(asset.correct_asset_pk, self.asset2.pk)
            self.assertEqual(asset.correct_asset_slug, self.asset2.slug)
            asset3 = response.context["assets_to_download"][1]
            self.assertFalse(hasattr(asset3, "correct_asset_pk"))
            self.assertFalse(hasattr(asset3, "correct_asset_slug"))

    def test_post_exception(self, task_mock, excel_mock):
        # Separate test from test_post_valid because the exception
        # prevents the assets_to_download context from being populated
        with tempfile.NamedTemporaryFile() as spreadsheet:
            spreadsheet.write(b"test")
            spreadsheet.seek(0)
            data = {
                "spreadsheet_file": spreadsheet,
            }

            rows = [
                [
                    mock.MagicMock(data_type="s", value="download_url"),
                    mock.MagicMock(data_type="s", value="real_file_url"),
                ],
                [
                    mock.MagicMock(data_type="s", value=self.asset.download_url),
                    mock.MagicMock(data_type="s", value=self.asset2.download_url),
                ],
            ]
            worksheet = mock.MagicMock(rows=iter(rows))
            excel_mock.return_value = mock.MagicMock()
            excel_mock.return_value.worksheets = [worksheet]

            # We should not get an exception because the view handles them
            # and messages the user
            task_mock.side_effect = ValueError

            response = self.client.post(self.url, data)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(excel_mock.called)
            self.assertTrue(task_mock.called)
            self.assertEqual(response.context["assets_to_download"], [])


class TestFunctionBasedViews(CreateTestUsers, TestCase):
    def test_admin_bulk_import_review(self):
        self.login_user(is_staff=True, is_superuser=True)
        self.assertTrue(self.user.is_active)
        self.assertTrue(self.user.is_staff)
        self.assertTrue(self.user.is_superuser)
        path = reverse("admin:bulk-review")
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)

        data = {}
        response = self.client.post(path, data=data)
        self.assertEqual(response.status_code, 200)


class TestSerializedObjectView(TestCase):
    def setUp(self):
        self.card = create_card()
        # Every test needs access to the request factory.
        self.factory = RequestFactory()

    def test_exists(self):
        request = self.factory.get(
            "/admin/card/",
            {"model_name": "Card", "object_id": self.card.id, "field_name": "title"},
        )
        response = SerializedObjectView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["title"], self.card.title)

    def test_dne(self):
        request = self.factory.get(
            "/admin/card/",
            {"model_name": "Card", "object_id": 2, "field_name": "title"},
        )
        response = SerializedObjectView.as_view()(request)
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertJSONEqual(response.content, {"status": "false"})
