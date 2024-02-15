from django.contrib.auth.models import User
from django.http import HttpRequest
from django.test import TestCase

from concordia.admin.actions import anonymize_action
from concordia.tests.utils import CreateTestUsers


class MockModelAdmin:
    pass


modeladmin = MockModelAdmin()
request = HttpRequest()


class UserAdminActionTest(TestCase, CreateTestUsers):
    def setUp(self):
        self.super_user = self.create_super_user("supertester")
        self.user1 = self.create_user("user1")
        self.user2 = self.create_user("user2")
        self.user3 = self.create_user("user3")

    def test_anonymize_action(self):
        queryset = User.objects.filter(pk__in=(self.user1.pk, self.user3.pk))
        anonymize_action(modeladmin, request, queryset)
        user1 = User.objects.get(pk=self.user1.pk)
        user2 = User.objects.get(pk=self.user2.pk)
        user3 = User.objects.get(pk=self.user3.pk)

        self.assertIn("Anonymized", user1.username)
        self.assertEqual(self.user2.username, user2.username)
        self.assertIn("Anonymized", user3.username)

        self.assertEqual("", user1.email)
        self.assertEqual(self.user2.email, user2.email)
        self.assertEqual("", user3.email)

        self.assertFalse(user1.has_usable_password())
        self.assertTrue(user2.has_usable_password())
        self.assertFalse(user3.has_usable_password())

        self.assertFalse(user1.check_password(self.user1._password))
        self.assertTrue(user2.check_password(self.user2._password))
        self.assertFalse(user3.check_password(self.user3._password))

        self.assertFalse(user1.is_active)
        self.assertTrue(user2.is_active)
        self.assertFalse(user3.is_active)
