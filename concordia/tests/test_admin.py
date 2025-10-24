import csv
import io
import zipfile
from datetime import date, datetime
from html import escape
from unittest import mock

from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.http import HttpResponse, HttpResponseRedirect
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import SafeString
from faker import Faker

from concordia.admin import (
    AssetAdmin,
    CampaignAdmin,
    CampaignRetirementProgressAdmin,
    ConcordiaUserAdmin,
    ItemAdmin,
    KeyMetricsReportAdmin,
    ProjectAdmin,
    ResourceFileAdmin,
    SiteReportAdmin,
    TagAdmin,
    TranscriptionAdmin,
)
from concordia.models import (
    Asset,
    Campaign,
    CampaignRetirementProgress,
    Item,
    KeyMetricsReport,
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
        user.profile.transcribe_count = 1
        user.profile.save()
        transcription_count = self.user_admin.transcription_count(user)
        self.assertEqual(transcription_count, 1)

    def test_review_count(self):
        request = self.request_factory.get("/")
        request.user = self.super_user
        users = self.user_admin.get_queryset(request)
        user = users.get(username=self.user.username)
        review_count = self.user_admin.review_count(user)
        self.assertEqual(review_count, 0)

        transcription = create_transcription(
            asset=self.asset, user=self.super_user, submitted=timezone.now()
        )
        transcription.accepted = timezone.now()
        transcription.reviewed_by = self.user
        transcription.save()
        user = users.get(username=self.user.username)
        user.profile.review_count = 1
        user.profile.save()
        review_count = self.user_admin.review_count(user)
        self.assertEqual(review_count, 1)

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
            + b"superuser status,last login,transcription count,review count",
            b"testsuperuser,testsuperuser@example.com,,,True,True,True,,0,0",
            b"testuser,testuser@example.com,,,True,False,False,,0,0",
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

    def test_campaign_admin(self):
        self.client.force_login(self.super_user)
        response = self.client.get(reverse("admin:concordia_campaign_add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "form")
        self.assertContains(response, "Display on homepage")
        self.assertContains(response, "Next transcription campaign")
        self.assertContains(response, "Next review campaign")


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
        self.assertEqual(result, "http://example.com")

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
        self.assertEqual(response.status_code, 403)
        self.client.logout()

        self.client.force_login(self.super_user)
        response = self.client.get(reverse(self.url_lookup, args=[self.project.id + 1]))
        self.assertEqual(response.status_code, 404)

        response = self.client.get(reverse(self.url_lookup, args=[self.project.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="admin/concordia/project/item_import.html"
        )

        self.client.post(
            reverse(self.url_lookup, args=[self.project.id]),
            {"bad_param": "https://example.com"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="admin/concordia/project/item_import.html"
        )

        with self.assertRaises(ValueError):
            self.client.post(
                reverse(self.url_lookup, args=[self.project.id]),
                {"import_url": "https://example.com"},
            )

        with mock.patch(
            "importer.tasks.items.create_item_import_task.delay"
        ) as task_mock:
            response = self.client.post(
                reverse(self.url_lookup, args=[self.project.id]),
                {"import_url": "https://www.loc.gov/item/example"},
            )
            self.assertTrue(task_mock.called)

        with mock.patch(
            "importer.tasks.collections.import_collection_task.delay"
        ) as task_mock:
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
        self.assertEqual(len(deleted_objects), 4)
        self.assertEqual(model_count, {"items": 50, "assets": 1, "transcriptions": 1})
        self.assertNotEqual(perms_needed, set())
        self.assertEqual(protected, [])

        request.user = self.super_user
        deleted_objects, model_count, perms_needed, protected = (
            self.admin.get_deleted_objects(mock_objs, request)
        )
        self.assertEqual(len(deleted_objects), 4)
        self.assertEqual(model_count, {"items": 50, "assets": 1, "transcriptions": 1})
        self.assertEqual(perms_needed, set())
        self.assertEqual(protected, [])

        deleted_objects, model_count, perms_needed, protected = (
            self.admin.get_deleted_objects([self.item], request)
        )
        self.assertEqual(len(deleted_objects), 1)
        self.assertEqual(model_count, {"items": 1, "assets": 1, "transcriptions": 1})
        self.assertEqual(perms_needed, set())
        self.assertEqual(protected, [])

    def test_get_queryset(self):
        request = self.request_factory.get("/")
        qs = self.admin.get_queryset(request)
        self.assertEqual(qs.count(), 1)

    def test_campaign_title(self):
        self.assertEqual(
            self.item.project.campaign.title, self.admin.campaign_title(self.item)
        )


class AssetAdminTest(TestCase, CreateTestUsers, StreamingTestMixin):
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
        self.assertEqual(qs.count(), 1)

    def test_lookup_allowed(self):
        self.assertTrue(self.admin.lookup_allowed("item__project__id__exact", 0))
        self.assertTrue(
            self.admin.lookup_allowed("item__project__campaign__id__exact", 0)
        )
        self.assertFalse(self.admin.lookup_allowed("item__project", 0))

    def test_item_id(self):
        self.assertEqual(self.asset.item.item_id, self.admin.item_id(self.asset))

    def test_export_to_csv(self):
        call_number = "A12.3.B4 C56 Vol. 789"
        contributor_names = "Records Collection (LOC)"
        lccn = "1234567890"
        original_format = "book, collection"
        repository = "LOC Collections"
        subject_headings = '["History", "Photography"]'
        self.asset.metadata = {
            "original_format": original_format,
        }
        self.asset.save()
        self.asset.item.metadata = {
            "item": {
                "call_number": call_number,
                "contributor_names": contributor_names,
                "library_of_congress_control_number": lccn,
                "repository": repository,
                "subject_headings": subject_headings,
            }
        }
        self.asset.item.save()

        request = self.request_factory.get("/")
        request.user = self.super_user

        response = self.admin.export_to_csv(request, self.admin.get_queryset(request))
        content = self.get_streaming_content(response).decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        row = next(reader)

        self.assertEqual(row["call_number"], call_number)
        self.assertEqual(row["contributor_names"], contributor_names)
        self.assertEqual(row["lccn_permalink"], f"https://lccn.loc.gov/{lccn}")
        self.assertEqual(row["original_format"], original_format)
        self.assertEqual(row["repository"], repository)
        self.assertEqual(row["subject_headings"], subject_headings)

    def test_truncated_storage_image(self):
        truncated_url = self.admin.truncated_storage_image(self.asset)
        filename = self.asset.get_existing_storage_image_filename()
        self.assertEqual(truncated_url.count(filename), 2)

        self.asset.storage_image.name = "".join([str(i) for i in range(200)])
        truncated_url = self.admin.truncated_storage_image(self.asset)
        filename = self.asset.get_existing_storage_image_filename()
        self.assertEqual(truncated_url.count(filename), 1)
        self.assertEqual(truncated_url.count(filename[:99]), 2)

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

    def test_has_reopen_permission(self):
        request = self.request_factory.get("/")
        request.user = self.super_user
        self.admin.has_reopen_permission(request)

        request.user = self.staff_user
        self.admin.has_reopen_permission(request)

    def test_response_action_redirects_with_valid_next(self):
        request = self.request_factory.post(
            reverse("admin:concordia_asset_changelist"),
            data={"next": "/admin/"},
        )
        request._messages = mock.MagicMock()
        request.user = self.super_user

        queryset = Asset.objects.all()
        admin_instance = AssetAdmin(Asset, self.site)
        admin_instance.get_actions = mock.MagicMock(return_value={})
        response = admin_instance.response_action(request, queryset)

        self.assertIsInstance(response, HttpResponseRedirect)
        self.assertEqual(response.url, "/admin/")

    def test_response_action_falls_back_to_default_without_valid_next(self):
        request = self.request_factory.post(
            reverse("admin:concordia_asset_changelist"),
            data={"next": "https://example.com/malicious"},
        )
        request._messages = mock.MagicMock()
        request.user = self.super_user

        queryset = Asset.objects.all()
        admin_instance = AssetAdmin(Asset, self.site)

        fallback_response = HttpResponseRedirect("/default/")
        with mock.patch.object(
            admin.ModelAdmin, "response_action", return_value=fallback_response
        ):
            response = admin_instance.response_action(request, queryset)

        self.assertEqual(response.url, "/default/")

    def test_change_view_skips_asset_logic_when_no_object_id(self):
        request = self.request_factory.get("/admin/concordia/asset/add/")
        request.user = self.super_user

        admin_instance = AssetAdmin(Asset, self.site)

        with mock.patch.object(
            admin.ModelAdmin, "change_view", return_value=HttpResponse("OK")
        ) as mock_super_change_view:
            response = admin_instance.change_view(request, object_id=None)

        self.assertEqual(response.status_code, 200)
        mock_super_change_view.assert_called_once()

    def test_change_view_handles_submitted_status_as_needs_review(self):
        asset = create_asset(
            item=self.asset.item, slug="test-asset-2", transcription_status="submitted"
        )
        request = self.request_factory.get(
            reverse("admin:concordia_asset_change", args=[asset.pk])
        )
        request.user = self.super_user

        admin_instance = AssetAdmin(Asset, self.site)

        with mock.patch.object(admin_instance, "get_actions") as mock_get_actions:
            mock_get_actions.return_value = {
                "change_status_to_completed": (
                    "func",
                    None,
                    "Change status to Completed",
                ),
                "change_status_to_needs_review": (
                    "func",
                    None,
                    "Change status to Needs Review",
                ),
                "change_status_to_in_progress": (
                    "func",
                    None,
                    "Change status to In Progress",
                ),
            }

            with mock.patch.object(
                admin.ModelAdmin, "change_view", return_value=HttpResponse("OK")
            ) as mock_super_change_view:
                response = admin_instance.change_view(request, str(asset.pk))

        self.assertEqual(response.status_code, 200)
        mock_super_change_view.assert_called_once()

    def test_response_action_returns_default_when_no_next_url(self):
        request = self.request_factory.post(
            reverse("admin:concordia_asset_changelist"),
            data={},
        )
        request._messages = mock.MagicMock()
        request.user = self.super_user

        queryset = Asset.objects.all()
        admin_instance = AssetAdmin(Asset, self.site)

        default_response = HttpResponseRedirect("/default/")
        with mock.patch.object(
            admin.ModelAdmin, "response_action", return_value=default_response
        ) as mock_super_response_action:
            response = admin_instance.response_action(request, queryset)

        mock_super_response_action.assert_called_once_with(request, queryset)
        self.assertEqual(response, default_response)
        self.assertEqual(response.url, "/default/")


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
            b"tag-value,%s,%i,%i,Test Asset,,,test-campaign"
            % (
                str.encode(mocked_datetime.isoformat()),
                self.user.id,
                self.collection.asset.id,
            ),
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
        self.assertEqual(result, self.transcription.text)

        self.transcription.text = self.fake.text(500)
        result = self.admin.truncated_text(self.transcription)
        self.assertNotEqual(result, self.transcription.text)
        self.assertIn(result[:-1], self.transcription.text)

    def test_export_to_csv(self):
        request = self.request_factory.get("/")
        request.user = self.super_user

        response = self.admin.export_to_csv(request, self.admin.get_queryset(request))
        content = self.get_streaming_content(response).split(b"\r\n")
        self.assertEqual(len(content), 3)
        test_data = [
            b"ID,asset__id,asset__slug,user,created on,updated on,supersedes,"
            + b"submitted,accepted,rejected,reviewed by,text,ocr generated,"
            + b"ocr originated",
            b"%i,%i,%s,%i,%s,%s,,,,,,,False,False"
            % (
                self.transcription.id,
                self.transcription.asset.id,
                str.encode(self.transcription.asset.slug),
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

    def test_show_full_result_count_is_disabled(self):
        self.assertFalse(self.admin.show_full_result_count)

    def test_list_display_includes_superseded(self):
        self.assertIn("superseded", self.admin.list_display)

    def test_list_filter_includes_superseded_param(self):
        params = {
            getattr(f, "parameter_name", None)
            for f in self.admin.list_filter
            if hasattr(f, "parameter_name")
        }
        self.assertIn("superseded", params)

    def test_get_queryset_adds_is_superseded_annotation(self):
        base = create_transcription(asset=self.asset, user=self.user, text="base")
        superseding = create_transcription(
            asset=self.asset, user=self.user, supersedes=base, text="superseding"
        )
        request = self.request_factory.get("/")
        qs = self.admin.get_queryset(request).filter(pk__in=[base.pk, superseding.pk])
        by_id = {t.pk: t for t in qs}
        self.assertIn(base.pk, by_id)
        self.assertIn(superseding.pk, by_id)
        self.assertTrue(hasattr(by_id[base.pk], "is_superseded"))
        self.assertTrue(by_id[base.pk].is_superseded)
        self.assertFalse(by_id[superseding.pk].is_superseded)

    def test_superseded_column_uses_annotation_boolean(self):
        base = create_transcription(asset=self.asset, user=self.user, text="base2")
        superseding = create_transcription(
            asset=self.asset, user=self.user, supersedes=base, text="superseding2"
        )
        request = self.request_factory.get("/")
        qs = self.admin.get_queryset(request).filter(pk__in=[base.pk, superseding.pk])
        by_id = {t.pk: t for t in qs}
        self.assertTrue(self.admin.superseded(by_id[base.pk]))
        self.assertFalse(self.admin.superseded(by_id[superseding.pk]))


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
            + b"assets started,items published,items unpublished,projects published,"
            + b"projects unpublished,anonymous transcriptions,transcriptions saved,"
            + b"daily review actions,distinct tags,tag uses,campaigns published,"
            + b"campaigns unpublished,users registered,users activated,"
            + b"registered contributors,daily active users",
            b"%s,,,,,,,,,,,,,,,,,,,,,,,,,,"
            % str.encode(self.mocked_datetime_formatted),
            b"",
        ]
        self.assertEqual(content, test_data)

    def test_export_to_excel(self):
        request = self.request_factory.get("/")
        request.user = self.super_user
        response = self.admin.export_to_excel(request, self.admin.get_queryset(request))
        # TODO: Test contents of file (requires a library to read xlsx files)
        self.assertNotEqual(len(response.content), 0)

    def test_report_type_variants(self):
        # Report name present
        s1 = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        text = self.admin.report_type(s1)
        self.assertIn("Report name", text)

        # Campaign present, no report name
        s2 = SiteReport.objects.create(campaign=self.campaign, report_name="")
        text = self.admin.report_type(s2)
        self.assertIn("Campaign", text)
        self.assertIn(self.campaign.title, text)

        # Topic present, no report name or campaign
        s3 = SiteReport.objects.create(topic=self.topic, report_name="", campaign=None)
        text = self.admin.report_type(s3)
        self.assertIn("Topic", text)
        self.assertIn(self.topic.title, text)

        # None of the above
        s4 = SiteReport.objects.create(report_name="", campaign=None, topic=None)
        text = self.admin.report_type(s4)
        self.assertIn("SiteReport:", text)
        self.assertIn(str(s4.id), text)

    def test_report_json_pretty_wrap(self):
        s = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        with mock.patch.object(SiteReport, "to_debug_json", return_value='{"a":1}'):
            html = self.admin.report_json(s)
        self.assertIn("<pre", html)
        self.assertIn("</pre>", html)
        self.assertIn(escape('{"a":1}'), html)

    def test_previous_and_next_in_series_links(self):
        # Build a small series of TOTAL snapshots with known timestamps.
        tz = timezone.get_current_timezone()
        t1 = timezone.make_aware(datetime(2024, 1, 1, 10, 0, 0), tz)
        t2 = timezone.make_aware(datetime(2024, 1, 1, 11, 0, 0), tz)
        t3 = timezone.make_aware(datetime(2024, 1, 1, 12, 0, 0), tz)

        a = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        b = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        c = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)

        # Set exact created_on values
        SiteReport.objects.filter(pk=a.pk).update(created_on=t1)
        SiteReport.objects.filter(pk=b.pk).update(created_on=t2)
        SiteReport.objects.filter(pk=c.pk).update(created_on=t3)

        # Refresh from DB to get updated created_on
        a = SiteReport.objects.get(pk=a.pk)
        b = SiteReport.objects.get(pk=b.pk)
        c = SiteReport.objects.get(pk=c.pk)

        # Middle record should link back to 'a' and forward to 'c'
        prev_html = self.admin.previous_in_series_link(b)
        next_html = self.admin.next_in_series_link(b)

        expected_prev_url = reverse(
            f"admin:{a._meta.app_label}_{a._meta.model_name}_change", args=[a.pk]
        )
        expected_prev_label = f"{a.created_on:%Y-%m-%d %H:%M:%S} (id {a.pk})"
        self.assertIn(expected_prev_url, prev_html)
        self.assertIn(expected_prev_label, prev_html)

        expected_next_url = reverse(
            f"admin:{c._meta.app_label}_{c._meta.model_name}_change", args=[c.pk]
        )
        expected_next_label = f"{c.created_on:%Y-%m-%d %H:%M:%S} (id {c.pk})"
        self.assertIn(expected_next_url, next_html)
        self.assertIn(expected_next_label, next_html)

        # Edge cases: first has no previous, last has no next
        self.assertEqual(self.admin.previous_in_series_link(a), "—")
        self.assertEqual(self.admin.next_in_series_link(c), "—")


class CampaignRetirementProgressAdminTest(TestCase):
    def setUp(self):
        class MockCompletion:
            complete = False

            project_total = 0
            item_total = 0
            asset_total = 0

            projects_removed = 0
            items_removed = 0
            assets_removed = 0

        self.completion_obj = MockCompletion()

        self.site = AdminSite()
        self.admin = CampaignRetirementProgressAdmin(
            model=CampaignRetirementProgress, admin_site=self.site
        )

    def test_completion(self):
        self.completion_obj.complete = True
        self.assertEqual(self.admin.completion(self.completion_obj), "100%")
        self.completion_obj.complete = False

        self.completion_obj.project_total = 10
        self.completion_obj.item_total = 100
        self.completion_obj.asset_total = 1000
        self.assertEqual(self.admin.completion(self.completion_obj), "0.0%")

        self.completion_obj.projects_removed = 1
        self.assertEqual(self.admin.completion(self.completion_obj), "0.09%")

        self.completion_obj.items_removed = 10
        self.completion_obj.assets_removed = 100
        self.assertEqual(self.admin.completion(self.completion_obj), "10.0%")


class KeyMetricsReportAdminTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.site = AdminSite()
        self.admin = KeyMetricsReportAdmin(model=KeyMetricsReport, admin_site=self.site)
        self.request_factory = RequestFactory()
        self.super_user = self.create_super_user()

    def _make_monthly(self):
        return KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
            month=1,
        )

    def test_download_csv_link_builds_expected_anchor(self):
        obj = self._make_monthly()
        html = self.admin.download_csv_link(obj)
        url = reverse("admin:concordia_keymetricsreport_download_csv", args=[obj.pk])
        self.assertIn('class="button"', html)
        self.assertIn("Download CSV", html)
        self.assertIn(url, html)

    def test_get_urls_registers_named_view(self):
        urls = self.admin.get_urls()
        names = [p.name for p in urls if hasattr(p, "name")]
        self.assertIn("concordia_keymetricsreport_download_csv", names)

    def test_download_csv_view_success(self):
        # Ensure monthly stage is computable in admin URLconf context
        SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)

        obj = self._make_monthly()

        with (
            mock.patch.object(
                KeyMetricsReport, "render_csv", return_value=b"a,b\n1,2\n"
            ),
            mock.patch.object(
                KeyMetricsReport, "csv_filename", return_value="report.csv"
            ),
        ):
            self.client.force_login(self.super_user)
            url = reverse(
                "admin:concordia_keymetricsreport_download_csv", args=[obj.pk]
            )
            resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn('attachment; filename="report.csv"', resp["Content-Disposition"])
        self.assertEqual(resp.content, b"a,b\n1,2\n")

    def test_download_csv_view_404_when_missing(self):
        # Login so admin view runs permission checks normally
        self.client.force_login(self.super_user)
        url = reverse(
            "admin:concordia_keymetricsreport_download_csv", args=["99999999"]
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_download_selected_as_zip_streams_zip_with_csvs(self):
        r1 = self._make_monthly()
        r2 = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=date(2024, 2, 1),
            period_end=date(2024, 2, 29),  # 2024 is leap year
            fiscal_year=2024,
            fiscal_quarter=2,
            month=2,
        )

        def fname_side_effect(self_obj):
            return f"kmr-{self_obj.pk}.csv"

        def csv_side_effect(self_obj):
            return f"id,{self_obj.pk}\n".encode("utf-8")

        with (
            mock.patch.object(
                KeyMetricsReport, "csv_filename", autospec=True
            ) as mock_fname,
            mock.patch.object(
                KeyMetricsReport, "render_csv", autospec=True
            ) as mock_csv,
        ):
            mock_fname.side_effect = fname_side_effect
            mock_csv.side_effect = csv_side_effect

            req = self.request_factory.post("/")
            req.user = self.super_user
            qs = KeyMetricsReport.objects.filter(pk__in=[r1.pk, r2.pk])

            resp = self.admin.download_selected_as_zip(req, qs)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/zip")
        self.assertIn(
            'attachment; filename="key_metrics_reports.zip"',
            resp["Content-Disposition"],
        )

        with zipfile.ZipFile(io.BytesIO(resp.content), "r") as zf:
            names = set(zf.namelist())
            self.assertIn(f"kmr-{r1.pk}.csv", names)
            self.assertIn(f"kmr-{r2.pk}.csv", names)
            self.assertEqual(
                zf.read(f"kmr-{r1.pk}.csv"), f"id,{r1.pk}\n".encode("utf-8")
            )
            self.assertEqual(
                zf.read(f"kmr-{r2.pk}.csv"), f"id,{r2.pk}\n".encode("utf-8")
            )
