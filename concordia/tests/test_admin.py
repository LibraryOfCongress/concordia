from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.test import TestCase

from concordia.admin import ConcordiaUserAdmin

from .utils import CreateTestUsers, create_asset, create_transcription


class MockRequest:
    pass


class MockSuperUser:
    def has_perm(self, perm, obj=None):
        return True


request = MockRequest()
request.user = MockSuperUser()


class ConcordiaUserAdminTest(TestCase, CreateTestUsers):
    def setUp(self):
        self.user_admin = ConcordiaUserAdmin(model=User, admin_site=AdminSite())
        self.user = self.create_user("useradmintester")
        self.asset = create_asset()

    def test_transcription_count(self):
        users = self.user_admin.get_queryset(request)
        user = users.get(username=self.user.username)
        transcription_count = self.user_admin.transcription_count(user)
        self.assertEqual(transcription_count, 0)

        create_transcription(asset=self.asset, user=user)
        user = users.get(username=self.user.username)
        transcription_count = self.user_admin.transcription_count(user)
        self.assertEqual(transcription_count, 1)
