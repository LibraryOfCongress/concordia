from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.test import TestCase
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


class MockRequest:
    pass


class MockSuperUser:
    def has_perm(self, perm, obj=None):
        return True


request = MockRequest()
request.user = MockSuperUser()


class ConcordiaUserAdminTest(TestCase, CreateTestUsers, StreamingTestMixin):
    def setUp(self):
        self.site = AdminSite()
        self.user = self.create_user("useradmintester")
        self.asset = create_asset()

    def get_user_admin(self):
        return ConcordiaUserAdmin(model=User, admin_site=self.site)

    def test_transcription_count(self):
        user_admin = self.get_user_admin()
        users = user_admin.get_queryset(request)
        user = users.get(username=self.user.username)
        transcription_count = user_admin.transcription_count(user)
        self.assertEqual(transcription_count, 0)

        create_transcription(asset=self.asset, user=user)
        user = users.get(username=self.user.username)
        transcription_count = user_admin.transcription_count(user)
        self.assertEqual(transcription_count, 1)

    def test_csv_export(self):
        user_admin = self.get_user_admin()
        # There's not a reasonable way to test `date_joined` so
        # we'll remove it to simplify the test
        user_admin.EXPORT_FIELDS = [
            field for field in user_admin.EXPORT_FIELDS if field != "date_joined"
        ]
        response = user_admin.export_users_as_csv(
            request, user_admin.get_queryset(request)
        )
        content = self.get_streaming_content(response).split(b"\r\n")
        self.assertEqual(len(content), 3)  # Includes empty line at the end of the file
        test_data = [
            b"username,email address,first name,last name,active,staff status,"
            + b"superuser status,last login,transcription__count",
            b"useradmintester,useradmintester@example.com,,,True,False,False,,0",
            b"",
        ]
        self.assertEqual(content, test_data)

    def test_excel_export(self):
        user_admin = self.get_user_admin()
        response = user_admin.export_users_as_excel(
            request, user_admin.get_queryset(request)
        )
        # TODO: Test contents of file (requires a library to read xlsx files)
        self.assertNotEqual(len(response.content), 0)


class CampaignAdminTest(TestCase, CreateTestUsers, StreamingTestMixin):
    def setUp(self):
        self.site = AdminSite()
        self.user = self.create_user("useradmintester")
        self.asset = create_asset()
        self.campaign = self.asset.item.project.campaign
        self.fake = Faker()

    def get_campaign_admin(self):
        return CampaignAdmin(model=Campaign, admin_site=self.site)

    def test_truncated_description(self):
        campaign_admin = self.get_campaign_admin()
        self.campaign.description = ""
        self.assertEqual(campaign_admin.truncated_description(self.campaign), "")
        self.campaign.description = self.fake.text()
        truncated_description = campaign_admin.truncated_metadata(self.campaign)
        self.assertIn(truncated_description, self.campaign.description)

    def test_truncated_metadata(self):
        campaign_admin = self.get_campaign_admin()
        self.campaign.metadata = {}
        self.assertEqual(campaign_admin.truncated_metadata(self.campaign), "")
        self.campaign.metadata[self.fake.unique.word()] = self.fake.text()
        truncated_metadata = campaign_admin.truncated_metadata(self.campaign)
        self.assertIs(type(truncated_metadata), SafeString)
        self.assertRegex(truncated_metadata, r"<code>.*</code>")
