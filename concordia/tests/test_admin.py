from unittest import mock

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import SafeString
from faker import Faker

from concordia.admin import (
    AssetAdmin,
    CampaignAdmin,
    ConcordiaUserAdmin,
    ItemAdmin,
    ProjectAdmin,
    ResourceFileAdmin,
    SiteReportAdmin,
    TagAdmin,
    TranscriptionAdmin,
)
from concordia.models import (
    Asset,
    Campaign,
    Item,
    Project,
    ResourceFile,
    SiteReport,
    Tag,
    Transcription,
)
from concordia.tests.utils import (
    CreateTestUsers,
    StreamingTestMixin,
    create_asset,
    create_project,
    create_site_report,
    create_tag_collection,
    create_topic,
    create_transcription,
)


class ConcordiaUserAdminTest(TestCase, CreateTestUsers, StreamingTestMixin):
    def setUp(self):
        self.site = AdminSite()
        self.user = self.create_test_user()
        self.super_user = self.create_super_user()
        self.asset = create_asset()
        self.user_admin = ConcordiaUserAdmin(model=User, admin_site=self.site)
        self.request_factory = RequestFactory()

    def test_transcription_count(self):
        request = self.request_factory.get("/")
        request.user = self.super_user
        users = self.user_admin.get_queryset(request)
        user = users.get(username=self.user.username)
        transcription_count = self.user_admin.transcription_count(user)
        self.assertEqual(transcription_count, 0)

        create_transcription(asset=self.asset, user=user)
        user = users.get(username=self.user.username)
        transcription_count = self.user_admin.transcription_count(user)
        self.assertEqual(transcription_count, 1)

    def test_csv_export(self):
        request = self.request_factory.get("/")
        request.user = self.super_user
        # TODO: Fix this to mock date_joined rather than removing it
        self.user_admin.EXPORT_FIELDS = [
            field for field in self.user_admin.EXPORT_FIELDS if field != "date_joined"
        ]
        response = self.user_admin.export_users_as_csv(
            request, self.user_admin.get_queryset(request)
        )
        content = self.get_streaming_content(response).split(b"\r\n")
        self.assertEqual(len(content), 4)  # Includes empty line at the end of the file
        test_data = [
            b"username,email address,first name,last name,active,staff status,"
            + b"superuser status,last login,transcription__count",
            b"testsuperuser,testsuperuser@example.com,,,True,True,True,,0",
            b"testuser,testuser@example.com,,,True,False,False,,0",
            b"",
        ]
        self.assertEqual(content, test_data)

    def test_excel_export(self):
        request = self.request_factory.get("/")
        request.user = self.super_user
        response = self.user_admin.export_users_as_excel(
            request, self.user_admin.get_queryset(request)
        )
        # TODO: Test contents of file (requires a library to read xlsx files)
        self.assertNotEqual(len(response.content), 0)


class CampaignAdminTest(TestCase, CreateTestUsers, StreamingTestMixin):
    def setUp(self):
        self.site = AdminSite()
        self.user = self.create_test_user()
        self.staff_user = self.create_staff_user()
        self.super_user = self.create_super_user()
        self.asset = create_asset()
        self.campaign = self.asset.item.project.campaign
        self.campaign_admin = CampaignAdmin(model=Campaign, admin_site=self.site)
        self.fake = Faker()
        self.request_factory = RequestFactory()

    def test_truncated_description(self):
        self.campaign.description = ""
        self.assertEqual(self.campaign_admin.truncated_description(self.campaign), "")
        self.campaign.description = self.fake.text()
        truncated_description = self.campaign_admin.truncated_metadata(self.campaign)
        self.assertIn(truncated_description, self.campaign.description)

    def test_truncated_metadata(self):
        self.campaign.metadata = {}
        self.assertEqual(self.campaign_admin.truncated_metadata(self.campaign), "")
        self.campaign.metadata[self.fake.unique.word()] = self.fake.text()
        truncated_metadata = self.campaign_admin.truncated_metadata(self.campaign)
        self.assertIs(type(truncated_metadata), SafeString)
        self.assertRegex(truncated_metadata, r"<code>.*</code>")

    def test_retire(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(
            reverse(
                "admin:concordia_campaign_retire",
                args=[
                    self.campaign.slug,
                ],
            )
        )
        self.assertEqual(response.status_code, 403)

        self.client.logout()
        self.client.force_login(self.super_user)
        response = self.client.get(
            reverse(
                "admin:concordia_campaign_retire", args=[self.campaign.slug + "bad"]
            )
        )
        self.assertEqual(response.status_code, 302)

        response = self.client.get(
            reverse("admin:concordia_campaign_retire", args=[self.campaign.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="admin/concordia/campaign/retire.html"
        )
        self.assertContains(response, "Are you sure?")

        response = self.client.post(
            reverse("admin:concordia_campaign_retire", args=[self.campaign.slug]),
            {"post": "yes"},
        )
        self.assertEqual(response.status_code, 302)
        campaign = Campaign.objects.get(pk=self.campaign.pk)
        self.assertEqual(campaign.status, Campaign.Status.RETIRED)


class ResourceAdminTest(TestCase, CreateTestUsers):
    def setUp(self):
        self.super_user = self.create_super_user()

    def test_resource_admin(self):
        self.client.force_login(self.super_user)
        response = self.client.get(reverse("admin:concordia_resource_add"))
        self.assertEqual(response.status_code, 200)


class ResourceFileAdminTest(TestCase, CreateTestUsers):
    def setUp(self):
        self.site = AdminSite()
        self.staff_user = self.create_staff_user()
        self.super_user = self.create_super_user()
        self.resource_file_admin = ResourceFileAdmin(
            model=ResourceFile, admin_site=self.site
        )
        self.request_factory = RequestFactory()

    def test_resource_url(self):
        class MockResource:
            url = "http://example.com?arg=true"

        class MockResourceFile:
            resource = MockResource()

        result = self.resource_file_admin.resource_url(MockResourceFile())
        self.assertEquals(result, "http://example.com")

    def test_get_fields(self):
        request = self.request_factory.get("/")
        result = self.resource_file_admin.get_fields(request)
        self.assertNotIn("path", result)
        self.assertNotIn("resource_url", result)

        result = self.resource_file_admin.get_fields(request, object())
        self.assertNotIn("path", result)
        self.assertIn("resource_url", result)


class ProjectAdminTest(TestCase, CreateTestUsers):
    def setUp(self):
        self.site = AdminSite()
        self.super_user = self.create_super_user()
        self.staff_user = self.create_staff_user()
        self.project_admin = ProjectAdmin(model=Project, admin_site=self.site)
        self.project = create_project()
        self.url_lookup = "admin:concordia_project_item-import"

    def test_lookup_allowed(self):
        self.assertTrue(self.project_admin.lookup_allowed("campaign__id__exact", 0))
        self.assertTrue(self.project_admin.lookup_allowed("campaign", 0))
        self.assertFalse(self.project_admin.lookup_allowed("campaign__slug__exact", 0))

    def test_item_import_view(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse(self.url_lookup, args=[self.project.id]))
        self.assertEquals(response.status_code, 403)
        self.client.logout()

        self.client.force_login(self.super_user)
        response = self.client.get(reverse(self.url_lookup, args=[self.project.id + 1]))
        self.assertEquals(response.status_code, 404)

        response = self.client.get(reverse(self.url_lookup, args=[self.project.id]))
        self.assertEquals(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="admin/concordia/project/item_import.html"
        )

        self.client.post(
            reverse(self.url_lookup, args=[self.project.id]),
            {"bad_param": "https://example.com"},
        )
        self.assertEquals(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="admin/concordia/project/item_import.html"
        )

        with self.assertRaises(ValueError):
            self.client.post(
                reverse(self.url_lookup, args=[self.project.id]),
                {"import_url": "https://example.com"},
            )

        with mock.patch("importer.tasks.create_item_import_task.delay") as task_mock:
            response = self.client.post(
                reverse(self.url_lookup, args=[self.project.id]),
                {"import_url": "https://www.loc.gov/item/example"},
            )
            self.assertTrue(task_mock.called)

        with mock.patch("importer.tasks.import_collection_task.delay") as task_mock:
            response = self.client.post(
                reverse(self.url_lookup, args=[self.project.id]),
                {"import_url": "https://www.loc.gov/collections/example/"},
            )
            self.assertTrue(task_mock.called)


class ItemAdminTest(TestCase, CreateTestUsers):
    def setUp(self):
        self.site = AdminSite()
        self.super_user = self.create_super_user()
        self.staff_user = self.create_staff_user()
        self.user = self.create_test_user()
        self.admin = ItemAdmin(model=Item, admin_site=self.site)
        self.asset = create_asset()
        self.item = self.asset.item
        create_transcription(asset=self.asset, user=self.user)
        self.request_factory = RequestFactory()

    def test_lookup_allowed(self):
        self.assertTrue(self.admin.lookup_allowed("project__campaign__id__exact", 0))
        self.assertFalse(self.admin.lookup_allowed("project__campaign", 0))
        self.assertFalse(self.admin.lookup_allowed("project__campaign__slug__exact", 0))

    def test_get_deleted_objects(self):
        mock_objs = range(0, 50)
        request = self.request_factory.get("/")

        request.user = self.staff_user
        deleted_objects, model_count, perms_needed, protected = (
            self.admin.get_deleted_objects(mock_objs, request)
        )
        self.assertEquals(len(deleted_objects), 4)
        self.assertEquals(model_count, {"items": 50, "assets": 1, "transcriptions": 1})
        self.assertNotEquals(perms_needed, set())
        self.assertEquals(protected, [])

        request.user = self.super_user
        deleted_objects, model_count, perms_needed, protected = (
            self.admin.get_deleted_objects(mock_objs, request)
        )
        self.assertEquals(len(deleted_objects), 4)
        self.assertEquals(model_count, {"items": 50, "assets": 1, "transcriptions": 1})
        self.assertEquals(perms_needed, set())
        self.assertEquals(protected, [])

        deleted_objects, model_count, perms_needed, protected = (
            self.admin.get_deleted_objects([self.item], request)
        )
        self.assertEquals(len(deleted_objects), 1)
        self.assertEquals(model_count, {"items": 1, "assets": 1, "transcriptions": 1})
        self.assertEquals(perms_needed, set())
        self.assertEquals(protected, [])

    def test_get_queryset(self):
        request = self.request_factory.get("/")
        qs = self.admin.get_queryset(request)
        self.assertEquals(qs.count(), 1)

    def test_campaign_title(self):
        self.assertEquals(
            self.item.project.campaign.title, self.admin.campaign_title(self.item)
        )


class AssetAdminTest(TestCase, CreateTestUsers):
    def setUp(self):
        self.site = AdminSite()
        self.super_user = self.create_super_user()
        self.staff_user = self.create_staff_user()
        self.user = self.create_test_user()
        self.admin = AssetAdmin(model=Asset, admin_site=self.site)
        self.asset = create_asset()
        create_transcription(asset=self.asset, user=self.user)
        self.request_factory = RequestFactory()

    def test_get_queryset(self):
        request = self.request_factory.get("/")
        qs = self.admin.get_queryset(request)
        self.assertEquals(qs.count(), 1)

    def test_lookup_allowed(self):
        self.assertTrue(self.admin.lookup_allowed("item__project__id__exact", 0))
        self.assertTrue(
            self.admin.lookup_allowed("item__project__campaign__id__exact", 0)
        )
        self.assertFalse(self.admin.lookup_allowed("item__project", 0))

    def test_item_id(self):
        self.assertEquals(self.asset.item.item_id, self.admin.item_id(self.asset))

    def test_truncated_media_url(self):
        truncated_url = self.admin.truncated_media_url(self.asset)
        self.assertEquals(truncated_url.count(self.asset.media_url), 2)

        self.asset.media_url = "".join([str(i) for i in range(200)])
        truncated_url = self.admin.truncated_media_url(self.asset)
        self.assertEquals(truncated_url.count(self.asset.media_url), 1)
        self.assertEquals(truncated_url.count(self.asset.media_url[:99]), 2)

    def test_get_readonly_fields(self):
        request = self.request_factory.get("/")
        self.assertNotIn("item", self.admin.get_readonly_fields(request))
        self.assertIn("item", self.admin.get_readonly_fields(request, self.asset))

    def test_change_view(self):
        self.client.force_login(self.super_user)
        response = self.client.get(
            reverse("admin:concordia_asset_change", args=[self.asset.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="admin/concordia/asset/change_form.html"
        )

        request = self.request_factory.get("/")
        request.user = self.super_user
        response = self.admin.change_view(request, str(self.asset.id))
        self.assertEqual(response.status_code, 200)

    def test_has_reopen_permission(self):
        request = self.request_factory.get("/")
        request.user = self.super_user
        self.admin.has_reopen_permission(request)

        request.user = self.staff_user
        self.admin.has_reopen_permission(request)


class TagAdminTest(TestCase, CreateTestUsers, StreamingTestMixin):
    def setUp(self):
        self.site = AdminSite()
        self.super_user = self.create_super_user()
        self.user = self.create_test_user()
        self.admin = TagAdmin(model=Tag, admin_site=self.site)
        self.request_factory = RequestFactory()

    def test_lookup_allowed(self):
        self.assertTrue(
            self.admin.lookup_allowed(
                "userassettagcollection__asset__item__project__campaign__id__exact", 0
            )
        )
        self.assertTrue(self.admin.lookup_allowed("id", 0))
        self.assertFalse(self.admin.lookup_allowed("userassettagcollection__asset", 0))

    def test_export_tags_as_csv(self):
        request = self.request_factory.get("/")
        request.user = self.super_user
        mocked_datetime = timezone.now()
        with mock.patch("django.utils.timezone.now") as now_mocked:
            now_mocked.return_value = mocked_datetime
            self.collection = create_tag_collection(user=self.user)

        response = self.admin.export_tags_as_csv(
            request, self.admin.get_queryset(request)
        )
        content = self.get_streaming_content(response).split(b"\r\n")
        self.assertEqual(len(content), 3)  # Includes empty line at the end of the file
        test_data = [
            b"tag value,user asset tag collection date created,"
            + b"user asset tag collection user_id,asset id,asset title,"
            + b"asset download url,asset resource url,campaign slug",
            b"tag-value,%s,%i,1,Test Asset,,,test-campaign"
            % (str.encode(mocked_datetime.isoformat()), self.user.id),
            b"",
        ]
        self.assertEqual(content, test_data)


class TranscriptionAdminTest(TestCase, CreateTestUsers, StreamingTestMixin):
    def setUp(self):
        self.site = AdminSite()
        self.super_user = self.create_super_user()
        self.user = self.create_test_user()
        self.asset = create_asset()
        self.mocked_datetime = timezone.now()
        self.mocked_datetime_formatted = self.mocked_datetime.isoformat()
        with mock.patch("django.utils.timezone.now") as now_mocked:
            now_mocked.return_value = self.mocked_datetime
            self.transcription = create_transcription(asset=self.asset, user=self.user)
        self.admin = TranscriptionAdmin(model=Transcription, admin_site=self.site)
        self.request_factory = RequestFactory()
        self.fake = Faker()

    def test_lookup_allowed(self):
        self.assertTrue(
            self.admin.lookup_allowed("asset__item__project__campaign__id__exact", 0)
        )
        self.assertTrue(self.admin.lookup_allowed("id", 0))
        self.assertFalse(
            self.admin.lookup_allowed("asset__item__project__id__exact", 0)
        )

    def test_truncated_text(self):
        self.transcription.text = self.fake.text(50)
        result = self.admin.truncated_text(self.transcription)
        self.assertEquals(result, self.transcription.text)

        self.transcription.text = self.fake.text(500)
        result = self.admin.truncated_text(self.transcription)
        self.assertNotEquals(result, self.transcription.text)
        self.assertIn(result[:-1], self.transcription.text)

    def test_export_to_csv(self):
        request = self.request_factory.get("/")
        request.user = self.super_user

        response = self.admin.export_to_csv(request, self.admin.get_queryset(request))
        content = self.get_streaming_content(response).split(b"\r\n")
        self.assertEqual(len(content), 3)  # Includes empty line at the end of the file
        test_data = [
            b"ID,asset__id,asset__slug,user,created on,updated on,supersedes,"
            + b"submitted,accepted,rejected,reviewed by,text,ocr generated,"
            + b"ocr originated",
            b"1,1,test-asset,%i,%s,%s,,,,,,,False,False"
            % (
                self.user.id,
                str.encode(self.mocked_datetime_formatted),
                str.encode(self.mocked_datetime_formatted),
            ),
            b"",
        ]
        self.assertEqual(content, test_data)

    def test_export_to_excel(self):
        request = self.request_factory.get("/")
        request.user = self.super_user
        response = self.admin.export_to_excel(request, self.admin.get_queryset(request))
        # TODO: Test contents of file (requires a library to read xlsx files)
        self.assertNotEqual(len(response.content), 0)


class SiteReportAdminTest(TestCase, CreateTestUsers, StreamingTestMixin):
    def setUp(self):
        self.site = AdminSite()
        self.super_user = self.create_super_user()
        self.mocked_datetime = timezone.now()
        self.mocked_datetime_formatted = self.mocked_datetime.isoformat()
        with mock.patch("django.utils.timezone.now") as now_mocked:
            now_mocked.return_value = self.mocked_datetime
            self.site_report = create_site_report()
        self.topic = create_topic()
        self.campaign = self.topic.project_set.all()[0].campaign
        self.admin = SiteReportAdmin(model=SiteReport, admin_site=self.site)
        self.request_factory = RequestFactory()
        self.fake = Faker()

    def test_report_type(self):
        self.site_report.report_name = "Test name"
        self.site_report.campaign = self.campaign
        self.site_report.topic = self.topic

        response = self.admin.report_type(self.site_report)
        self.assertIn("Report name", response)

        self.site_report.report_name = ""
        response = self.admin.report_type(self.site_report)
        self.assertIn("Campaign", response)

        self.site_report.campaign = None
        response = self.admin.report_type(self.site_report)
        self.assertIn("Topic", response)

        self.site_report.topic = None
        response = self.admin.report_type(self.site_report)
        self.assertIn("SiteReport", response)

    def test_export_to_csv(self):
        request = self.request_factory.get("/")
        request.user = self.super_user

        response = self.admin.export_to_csv(request, self.admin.get_queryset(request))
        content = self.get_streaming_content(response).split(b"\r\n")
        self.assertEqual(len(content), 3)  # Includes empty line at the end of the file
        test_data = [
            b"created on,report name,campaign__title,topic__title,assets total,"
            + b"assets published,assets not started,assets in progress,"
            + b"assets waiting review,assets completed,assets unpublished,"
            + b"items published,items unpublished,projects published,"
            + b"projects unpublished,anonymous transcriptions,transcriptions saved,"
            + b"daily review actions,distinct tags,tag uses,campaigns published,"
            + b"campaigns unpublished,users registered,users activated,"
            + b"registered contributors,daily active users",
            b"%s,,,,,,,,,,,,,,,,,,,,,,,,," % str.encode(self.mocked_datetime_formatted),
            b"",
        ]
        self.assertEqual(content, test_data)

    def test_export_to_excel(self):
        request = self.request_factory.get("/")
        request.user = self.super_user
        response = self.admin.export_to_excel(request, self.admin.get_queryset(request))
        # TODO: Test contents of file (requires a library to read xlsx files)
        self.assertNotEqual(len(response.content), 0)
