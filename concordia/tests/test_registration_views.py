"""
Tests for user registration-related views
"""
import unittest
from logging import getLogger
from secrets import token_hex

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .utils import CacheControlAssertions, CreateTestUsers, JSONAssertMixin

User = get_user_model()


logger = getLogger(__name__)


INTERNAL_RESET_URL_TOKEN = "set-password"
INTERNAL_RESET_SESSION_TOKEN = "_password_reset_token"


@override_settings(RATELIMIT_ENABLE=False)
class ConcordiaViewTests(
    JSONAssertMixin, CacheControlAssertions, TestCase, CreateTestUsers
):
    def test_send_activation_email_on_inactive_login(self):
        self.user = self.create_inactive_user("tester")

        response = self.client.post(
            reverse("registration_login"),
            {"username": self.user.username, "password": self.user.password},
        )

        self.assertContains(
            response,
            "Please check your email and click the link to activate your account.",
        )

        self.assertEqual(len(mail.outbox), 1)

    def test_inactive_user_can_password_reset(self):
        self.user = self.create_inactive_user("tester")

        self.client.post(reverse("password_reset"), {"email": self.user.email})

        self.assertEqual(len(mail.outbox), 1)

    @unittest.skip
    def test_password_reset_will_activate_user(self):
        self.user = self.create_inactive_user("tester2")
        fake_pw = token_hex(24)
        new_password_data = {"new_password1": fake_pw, "new_password2": fake_pw}
        password_reset_token = default_token_generator.make_token(self.user)
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))

        session = self.client.session
        session[INTERNAL_RESET_SESSION_TOKEN] = password_reset_token
        session.save()

        confirm_response = self.client.post(
            reverse(
                "password_reset_confirm",
                kwargs={"uidb64": uidb64, "token": INTERNAL_RESET_URL_TOKEN},
            ),
            new_password_data,
        )

        self.assertEqual(confirm_response.status_code, 200)
        self.assertTemplateUsed(
            confirm_response, template_name="registration/password_reset_complete.html"
        )
        self.assertUncacheable(confirm_response)

        # Verify the User was correctly activated
        updated_user = User.objects.get(pk=self.user.pk)
        self.assertEqual(updated_user.is_active, True)
