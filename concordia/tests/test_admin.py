from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.test import TestCase

from concordia.admin import ConcordiaUserAdmin
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
        # There's not a reasonable way to test `date_joined` so we'll remove it
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
        # There's not a reasonable way to test `date_joined` so we'll remove it
        user_admin.EXPORT_FIELDS = [
            field for field in user_admin.EXPORT_FIELDS if field != "date_joined"
        ]
        response = user_admin.export_users_as_excel(
            request, user_admin.get_queryset(request)
        )
        # TODO: Test contents of file (requires a library to read xlsx files)
        self.assertNotEqual(len(response.content), 0)
