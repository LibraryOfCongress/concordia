import copy
import json
import tempfile
from http import HTTPStatus
from io import BytesIO
from unittest import mock

from django.contrib.messages import get_messages
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from concordia.admin.views import SerializedObjectView
from concordia.models import Campaign, Project
from concordia.tests.utils import (
    CreateTestUsers,
    StreamingTestMixin,
    create_asset,
    create_card,
    create_site_report,
)


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


class TestProjectLevelExportView(CreateTestUsers, TestCase):
    def setUp(self):
        self.login_user(is_staff=True, is_superuser=True)
        self.url = reverse("admin:project-level-export")
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

    def test_get(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, f"<td>{self.asset.item.project.campaign.title}</td>", html=True
        )

    def test_get_campaign(self):
        response = self.client.get(
            self.url, {"id": self.asset.item.project.campaign.id}
        )
        self.assertContains(
            response, f"<td>{self.asset.item.project.title}</td>", html=True
        )

    def test_post(self):
        with mock.patch("exporter.views.boto3.resource", autospec=True) as bucket_mock:
            # The parameter is 'project_name', but it actually expects the project id.
            response = self.client.post(
                f"{self.url}?slug={self.asset.item.project.campaign.slug}",
                {"project_name": f"{self.asset.item.project.id}"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "application/zip")
            self.assertFalse(bucket_mock.called)


class TestFunctionBasedViews(CreateTestUsers, TestCase, StreamingTestMixin):
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

    def test_admin_site_report_view(self):
        self.login_user(is_staff=True, is_superuser=True)
        mocked_datetime = timezone.now()
        mocked_datetime_formatted = mocked_datetime.isoformat()
        with mock.patch("django.utils.timezone.now") as now_mocked:
            now_mocked.return_value = mocked_datetime
            create_site_report()

        response = self.client.get(reverse("admin:site-report"))
        self.assertEqual(response.status_code, 200)
        content = self.get_streaming_content(response).split(b"\r\n")
        self.assertEqual(len(content), 3)  # Includes empty line at the end of the file
        test_data = [
            b"Date,report name,Campaign,topic__title,assets total,assets published,"
            b"assets not started,assets in progress,assets waiting review,"
            b"assets completed,assets unpublished,items published,items unpublished,"
            b"projects published,projects unpublished,anonymous transcriptions,"
            b"transcriptions saved,daily review actions,distinct tags,tag uses,"
            b"campaigns published,campaigns unpublished,users registered,"
            b"users activated,registered contributors,daily active users",
            b"%s,,,,,,,,,,,,,,,,,,,,,,,,," % str.encode(mocked_datetime_formatted),
            b"",
        ]
        self.assertEqual(content, test_data)

    def test_admin_retired_site_report_view(self):
        self.login_user(is_staff=True, is_superuser=True)

        response = self.client.get(reverse("admin:retired-site-report"))
        self.assertEqual(response.status_code, 200)
        content = self.get_streaming_content(response).split(b"\r\n")
        self.assertEqual(len(content), 3)  # Includes empty line at the end of the file
        test_data = [
            b"Date,report name,Campaign,topic__title,assets total,assets published,"
            b"assets not started,assets in progress,assets waiting review,"
            b"assets completed,assets unpublished,items published,items unpublished,"
            b"projects published,projects unpublished,anonymous transcriptions,"
            b"transcriptions saved,daily review actions,distinct tags,tag uses,"
            b"campaigns published,campaigns unpublished,users registered,"
            b"users activated,registered contributors,daily active users",
            b",RETIRED TOTAL,,,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0",
            b"",
        ]
        self.assertEqual(content, test_data)


class TestAdminBulkImportView(CreateTestUsers, TestCase):
    def setUp(self):
        self.login_user(is_staff=True, is_superuser=True)
        self.path = reverse("admin:bulk-import")
        self.campaign_title = "Test Campaign"
        self.campaign_short_description = "Short description"
        self.campaign_long_description = "Long description"
        self.campaign_slug = "test-campaign"
        self.project_slug = "test-project"
        self.project_title = "Test Project"
        self.project_description = "Project description"
        self.url = "http://example.com"
        self.spreadsheet_data = {
            "Campaign": self.campaign_title,
            "Campaign Short Description": self.campaign_short_description,
            "Campaign Long Description": self.campaign_long_description,
            "Campaign Slug": self.campaign_slug,
            "Project Slug": self.project_slug,
            "Project": self.project_title,
            "Project Description": self.project_description,
            "Import URLs": self.url,
        }
        self.post_data = {"spreadsheet_file": BytesIO()}

    def test_get(self):
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)

    def test_invalid_form(self):
        response = self.client.post(self.path)
        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)

    def test_fully_valid_form(self):
        with (
            mock.patch(
                "concordia.admin.views.AdminProjectBulkImportForm", autospec=True
            ) as form_mock,
            mock.patch(
                "concordia.admin.views.slurp_excel", autospec=True
            ) as slurp_mock,
            mock.patch(
                "concordia.admin.views.import_items_into_project_from_url",
                autospec=True,
            ),
        ):
            form_mock.return_value.is_valid.return_value = True
            form_mock.return_value.cleaned_data = {}
            slurp_mock.return_value = [self.spreadsheet_data]

            response = self.client.post(self.path, data=self.post_data)

            self.assertEqual(response.status_code, 200)
            messages = [str(message) for message in get_messages(response.wsgi_request)]
            self.assertEqual(len(messages), 3)
            self.assertEqual(messages[0], f"Created new campaign {self.campaign_title}")
            self.assertEqual(messages[1], f"Created new project {self.project_title}")
            self.assertEqual(
                messages[2],
                f"Queued {self.campaign_title} {self.project_title} "
                f"import for {self.url}",
            )

            campaign = Campaign.objects.get()
            self.assertEqual(campaign.title, self.campaign_title)
            self.assertEqual(campaign.slug, self.campaign_slug)
            self.assertEqual(campaign.description, self.campaign_long_description)
            self.assertEqual(
                campaign.short_description, self.campaign_short_description
            )

            project = Project.objects.get()
            self.assertEqual(project.title, self.project_title)
            self.assertEqual(project.slug, self.project_slug)
            self.assertEqual(project.description, self.project_description)

            # Submit it again to test that it doesn't re-create the campaign or project
            response = self.client.post(self.path, data=self.post_data)
            self.assertEqual(response.status_code, 200)
            messages = [str(message) for message in get_messages(response.wsgi_request)]
            self.assertEqual(len(messages), 3)
            self.assertEqual(
                messages[0],
                f"Reusing campaign {self.campaign_title} without modification",
            )
            self.assertEqual(
                messages[1],
                f"Reusing project {self.project_title} without modification",
            )
            self.assertEqual(
                messages[2],
                f"Queued {self.campaign_title} {self.project_title} "
                f"import for {self.url}",
            )
            self.assertEqual(1, Campaign.objects.count())
            self.assertEqual(1, Project.objects.count())

    def test_missing_field(self):
        spreadsheet_data = copy.copy(self.spreadsheet_data)
        del spreadsheet_data["Campaign"]

        with (
            mock.patch(
                "concordia.admin.views.AdminProjectBulkImportForm", autospec=True
            ) as form_mock,
            mock.patch(
                "concordia.admin.views.slurp_excel", autospec=True
            ) as slurp_mock,
            mock.patch(
                "concordia.admin.views.import_items_into_project_from_url",
                autospec=True,
            ),
        ):
            form_mock.return_value.is_valid.return_value = True
            form_mock.return_value.cleaned_data = {}
            slurp_mock.return_value = [spreadsheet_data]

            response = self.client.post(self.path, data=self.post_data)

        self.assertEqual(response.status_code, 200)
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertEqual(len(messages), 1)
        self.assertEqual(
            str(messages[0]), "Skipping row 0: missing fields ['Campaign']"
        )

    def test_empty_field(self):
        # Only three fields require values: Campaign, Projet and Import URLs.
        # Other fields must be present but can be empty.
        # This tests that blank value check
        spreadsheet_data = copy.copy(self.spreadsheet_data)

        with (
            mock.patch(
                "concordia.admin.views.AdminProjectBulkImportForm", autospec=True
            ) as form_mock,
            mock.patch(
                "concordia.admin.views.slurp_excel", autospec=True
            ) as slurp_mock,
            mock.patch(
                "concordia.admin.views.import_items_into_project_from_url",
                autospec=True,
            ),
        ):
            form_mock.return_value.is_valid.return_value = True
            form_mock.return_value.cleaned_data = {}

            # Test one empty field
            spreadsheet_data["Campaign"] = ""
            slurp_mock.return_value = [spreadsheet_data]

            response = self.client.post(self.path, data=self.post_data)
            self.assertEqual(response.status_code, 200)
            messages = [str(message) for message in get_messages(response.wsgi_request)]
            self.assertEqual(len(messages), 1)
            self.assertEqual(
                messages[0],
                "Skipping row 0: at least one required field "
                "(Campaign, Project, Import URLs) is empty",
            )

    def test_all_empty_fields(self):
        # If all values in a spreadsheet row are empty, the row is skipped silently
        spreadsheet_data = {key: "" for key in self.spreadsheet_data.keys()}

        with (
            mock.patch(
                "concordia.admin.views.AdminProjectBulkImportForm", autospec=True
            ) as form_mock,
            mock.patch(
                "concordia.admin.views.slurp_excel", autospec=True
            ) as slurp_mock,
            mock.patch(
                "concordia.admin.views.import_items_into_project_from_url",
                autospec=True,
            ),
        ):
            form_mock.return_value.is_valid.return_value = True
            form_mock.return_value.cleaned_data = {}
            slurp_mock.return_value = [spreadsheet_data]

            response = self.client.post(self.path, data=self.post_data)

        self.assertEqual(response.status_code, 200)
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertEqual(len(messages), 0)

    def test_empty_campaign_slug(self):
        spreadsheet_data = copy.copy(self.spreadsheet_data)
        spreadsheet_data["Campaign Slug"] = ""

        with (
            mock.patch(
                "concordia.admin.views.AdminProjectBulkImportForm", autospec=True
            ) as form_mock,
            mock.patch(
                "concordia.admin.views.slurp_excel", autospec=True
            ) as slurp_mock,
            mock.patch(
                "concordia.admin.views.import_items_into_project_from_url",
                autospec=True,
            ),
        ):
            form_mock.return_value.is_valid.return_value = True
            form_mock.return_value.cleaned_data = {}
            slurp_mock.return_value = [spreadsheet_data]

            response = self.client.post(self.path, data=self.post_data)

        self.assertEqual(response.status_code, 200)
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0], f"Created new campaign {self.campaign_title}")
        self.assertEqual(messages[1], f"Created new project {self.project_title}")
        self.assertEqual(
            messages[2],
            f"Queued {self.campaign_title} {self.project_title} import for {self.url}",
        )

        # Since the provided campaign slug was blank, it should slugify the Campaign
        # field instead
        campaign = Campaign.objects.get()
        self.assertEqual(
            campaign.slug, slugify(self.campaign_title, allow_unicode=True)
        )

    def test_bad_campaign_slug(self):
        spreadsheet_data = copy.copy(self.spreadsheet_data)
        spreadsheet_data["Campaign Slug"] = "bad#slug@"

        with (
            mock.patch(
                "concordia.admin.views.AdminProjectBulkImportForm", autospec=True
            ) as form_mock,
            mock.patch(
                "concordia.admin.views.slurp_excel", autospec=True
            ) as slurp_mock,
            mock.patch(
                "concordia.admin.views.import_items_into_project_from_url",
                autospec=True,
            ),
        ):
            form_mock.return_value.is_valid.return_value = True
            form_mock.return_value.cleaned_data = {}
            slurp_mock.return_value = [spreadsheet_data]

            response = self.client.post(self.path, data=self.post_data)

        self.assertEqual(response.status_code, 200)
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0], "Campaign slug doesn't match pattern.")
        self.assertEqual(
            messages[1],
            "Unable to create campaign Test Campaign: {'slug': "
            "['Enter a valid “slug” consisting of Unicode letters, "
            "numbers, underscores, or hyphens.']}",
        )

    def test_empty_project_slug(self):
        spreadsheet_data = copy.copy(self.spreadsheet_data)
        spreadsheet_data["Project Slug"] = ""

        with (
            mock.patch(
                "concordia.admin.views.AdminProjectBulkImportForm", autospec=True
            ) as form_mock,
            mock.patch(
                "concordia.admin.views.slurp_excel", autospec=True
            ) as slurp_mock,
            mock.patch(
                "concordia.admin.views.import_items_into_project_from_url",
                autospec=True,
            ),
        ):
            form_mock.return_value.is_valid.return_value = True
            form_mock.return_value.cleaned_data = {}
            slurp_mock.return_value = [spreadsheet_data]

            response = self.client.post(self.path, data=self.post_data)

        self.assertEqual(response.status_code, 200)
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0], f"Created new campaign {self.campaign_title}")
        self.assertEqual(messages[1], f"Created new project {self.project_title}")
        self.assertEqual(
            messages[2],
            f"Queued {self.campaign_title} {self.project_title} import for {self.url}",
        )

        # Since the provided project slug was blank, it should slugify the project
        # field instead
        project = Project.objects.get()
        self.assertEqual(project.slug, slugify(self.project_title, allow_unicode=True))

    def test_bad_project_slug(self):
        spreadsheet_data = copy.copy(self.spreadsheet_data)
        spreadsheet_data["Project Slug"] = "bad#slug@"

        with (
            mock.patch(
                "concordia.admin.views.AdminProjectBulkImportForm", autospec=True
            ) as form_mock,
            mock.patch(
                "concordia.admin.views.slurp_excel", autospec=True
            ) as slurp_mock,
            mock.patch(
                "concordia.admin.views.import_items_into_project_from_url",
                autospec=True,
            ),
        ):
            form_mock.return_value.is_valid.return_value = True
            form_mock.return_value.cleaned_data = {}
            slurp_mock.return_value = [spreadsheet_data]

            response = self.client.post(self.path, data=self.post_data)

        self.assertEqual(response.status_code, 200)
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0], f"Created new campaign {self.campaign_title}")
        self.assertEqual(messages[1], "Project slug doesn't match pattern.")
        self.assertEqual(
            messages[2],
            "Unable to create project Test Project: {'slug': "
            "['Enter a valid “slug” consisting of Unicode letters, "
            "numbers, underscores, or hyphens.']}",
        )

    def test_bad_url(self):
        spreadsheet_data = copy.copy(self.spreadsheet_data)
        spreadsheet_data["Import URLs"] = bad_url = "ftp://example.com"

        with (
            mock.patch(
                "concordia.admin.views.AdminProjectBulkImportForm", autospec=True
            ) as form_mock,
            mock.patch(
                "concordia.admin.views.slurp_excel", autospec=True
            ) as slurp_mock,
            mock.patch(
                "concordia.admin.views.import_items_into_project_from_url",
                autospec=True,
            ),
        ):
            form_mock.return_value.is_valid.return_value = True
            form_mock.return_value.cleaned_data = {}
            slurp_mock.return_value = [spreadsheet_data]

            response = self.client.post(self.path, data=self.post_data)

        self.assertEqual(response.status_code, 200)
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0], f"Created new campaign {self.campaign_title}")
        self.assertEqual(messages[1], f"Created new project {self.project_title}")
        self.assertEqual(messages[2], f"Skipping unrecognized URL value: {bad_url}")

    def test_import_task_exception(self):
        with (
            mock.patch(
                "concordia.admin.views.AdminProjectBulkImportForm", autospec=True
            ) as form_mock,
            mock.patch(
                "concordia.admin.views.slurp_excel", autospec=True
            ) as slurp_mock,
            mock.patch(
                "concordia.admin.views.import_items_into_project_from_url",
                autospec=True,
            ) as import_mock,
        ):
            form_mock.return_value.is_valid.return_value = True
            form_mock.return_value.cleaned_data = {}
            slurp_mock.return_value = [self.spreadsheet_data]
            import_mock.side_effect = Exception("Test Exception")

            response = self.client.post(self.path, data=self.post_data)

            self.assertEqual(response.status_code, 200)
            messages = [str(message) for message in get_messages(response.wsgi_request)]
            self.assertEqual(len(messages), 3)
            self.assertEqual(messages[0], f"Created new campaign {self.campaign_title}")
            self.assertEqual(messages[1], f"Created new project {self.project_title}")
            self.assertEqual(
                messages[2],
                f"Unhandled error attempting to import {self.url}: Test Exception",
            )


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
            {"model_name": "Card", "object_id": 3, "field_name": "title"},
        )
        response = SerializedObjectView.as_view()(request)
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertJSONEqual(response.content, {"status": "false"})
