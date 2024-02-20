from unittest import mock

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils.safestring import SafeString
from faker import Faker

from concordia.admin import (
    AssetAdmin,
    CampaignAdmin,
    ConcordiaUserAdmin,
    ItemAdmin,
    ProjectAdmin,
    ResourceFileAdmin,
)
from concordia.models import Asset, Campaign, Item, Project, ResourceFile
from concordia.tests.utils import (
    CreateTestUsers,
    StreamingTestMixin,
    create_asset,
    create_project,
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
        # There's not a reasonable way to test `date_joined` so
        # we'll remove it to simplify the test
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
