"""Tests for Concordia middleware components.

Validates Cloudflare authentication status cookie issuance, HMAC signature
verification, setting overrides, and structured logging events.
"""

from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.test import TestCase, override_settings
from django.urls import reverse

from concordia.middleware import CloudflareAuthStatusMiddleware

User = get_user_model()


class CloudflareAuthStatusMiddlewareTests(TestCase):
    def setUp(self):
        """Set up test user and middleware constants."""
        self.user = User.objects.create_user(
            username="testuser",
            email="testuser@test.com",
            password="TestPassword123!",  # nosec
        )
        self.salt = CloudflareAuthStatusMiddleware.SIGNING_SALT

    @property
    def cookie_name(self):
        """Return configured cookie name from settings or default."""
        return getattr(settings, "CLOUDFLARE_AUTH_STATUS_COOKIE_NAME", "_cf_acc_status")

    def test_anonymous_user_does_not_receive_cookie(self):
        response = self.client.get(reverse("homepage"))
        self.assertNotIn(self.cookie_name, response.cookies)

    def test_authenticated_user_receives_signed_cookie(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("homepage"))

        self.assertIn(self.cookie_name, response.cookies)

        cookie_val = response.cookies[self.cookie_name].value
        self.client.cookies[self.cookie_name] = cookie_val

        data = signing.loads(cookie_val, salt=self.salt)

        self.assertEqual(data["uid"], self.user.pk)

    @override_settings(CLOUDFLARE_AUTH_STATUS_COOKIE_NAME="_cf_rot_token")
    def test_configurable_cookie_name_from_settings(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("homepage"))

        self.assertIn("_cf_rot_token", response.cookies)
        self.assertNotIn("_cf_acc_status", response.cookies)

    def test_valid_existing_cookie_is_preserved(self):
        self.client.force_login(self.user)

        # First request sets the cookie
        response_1 = self.client.get(reverse("homepage"))
        initial_cookie_val = response_1.cookies[self.cookie_name].value

        # Second request presents the valid cookie back to the middleware
        self.client.cookies[self.cookie_name] = initial_cookie_val
        response_2 = self.client.get(reverse("homepage"))

        # Middleware should validate signature and not force a new set-cookie header
        self.assertNotIn(self.cookie_name, response_2.cookies)

    def test_cookie_deleted_on_logout(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("homepage"))
        cookie_val = response.cookies[self.cookie_name].value

        # Attach active cookie to client and perform logout
        self.client.cookies[self.cookie_name] = cookie_val
        response = self.client.post(reverse("logout"))

        self.assertIn(self.cookie_name, response.cookies)
        self.assertEqual(response.cookies[self.cookie_name].value, "")

    def test_forged_or_invalid_signature_is_overwritten_and_logged(self):
        self.client.force_login(self.user)

        # Inject fake/spoofed signature cookie
        self.client.cookies[self.cookie_name] = "fake_signature_value"
        response = self.client.get(reverse("homepage"))

        self.assertIn(self.cookie_name, response.cookies)
        new_value = response.cookies[self.cookie_name].value
        self.assertNotEqual(new_value, "fake_signature_value")

    @patch("concordia.middleware.structured_logger.warning")
    def test_corrupt_payload_is_overwritten_and_logged(self, mock_logger):
        self.client.force_login(self.user)

        corrupt_payload = "not_valid_json_payload"
        # Sign a non-dict value so signature validation succeeds but payload
        # validation fails.
        signed_value = signing.dumps(corrupt_payload, salt=self.salt)

        # Attach the validly signed (but corrupt JSON) cookie to the client
        self.client.cookies[self.cookie_name] = signed_value
        response = self.client.get(reverse("homepage"))

        self.assertIn(self.cookie_name, response.cookies)
        new_value = response.cookies[self.cookie_name].value
        self.assertNotEqual(new_value, signed_value)

        # Verify structured logger corrupt payload warning call
        mock_logger.assert_called_once()
        self.assertEqual(
            mock_logger.call_args.kwargs["event_code"],
            "cloudflare_auth_cookie_corrupt_payload",
        )
