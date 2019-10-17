"""
Tests for user registration-related views
"""
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .utils import CacheControlAssertions, CreateTestUsers, JSONAssertMixin


@override_settings(RATELIMIT_ENABLE=False)
class ConcordiaViewTests(
    JSONAssertMixin, CacheControlAssertions, TestCase, CreateTestUsers
):
    def test_inactiveUserCanPasswordReset(self):
        """
        Test the ability to activate a user account based on password reset
        """
        self.user = self.create_inactive_user("tester")

        self.client.post(reverse("password_reset"), {"email": self.user.email})

        self.assertEqual(len(mail.outbox), 1)


#    def test_userActivationViaEmailConfirmation(self):
#        self.user = self.create_inactive_user("tester")
