from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.utils.safestring import SafeString
from faker import Faker

from concordia.admin import CampaignAdmin, ConcordiaUserAdmin
from concordia.models import Campaign
from concordia.tests.utils import (
    CreateTestUsers,
    StreamingTestMixin,
    create_asset,
    create_transcription,
)


class ConcordiaUserAdminTest(TestCase, CreateTestUsers, StreamingTestMixin):
    def setUp(self):
        self.site = AdminSite()
        self.user = self.create_user("useradmintester")
        self.super_user = self.create_super_user("testsuperuser")
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
            b"testsuperuser,testsuperuser@example.com,,,True,False,True,,0",
            b"useradmintester,useradmintester@example.com,,,True,False,False,,0",
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
        self.user = self.create_user("useradmintester")
        self.super_user = self.create_super_user("testsuperuser")
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
        with self.assertRaises(PermissionDenied):
            request = self.request_factory.get("/")
            request.user = self.user
            self.campaign_admin.retire(request, self.campaign.slug)
        # TODO: Implement test of authorized user
