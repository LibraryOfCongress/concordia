import json
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import TestCase, override_settings
from django.urls import reverse

from concordia.middleware import CloudflareAuthStatusMiddleware

User = get_user_model()


class CloudflareAuthStatusMiddlewareTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="testuser@test.com",
            password="TestPassword123!",  # nosec
        )
        self.salt = CloudflareAuthStatusMiddleware.SIGNING_SALT

    @property
    def cookie_name(self):
        return getattr(settings, "CLOUDFLARE_AUTH_STATUS_COOKIE_NAME", "_cf_acc_status")

    def test_anonymous_user_does_not_receive_cookie(self):
        response = self.client.get(reverse("homepage"))
        self.assertNotIn(self.cookie_name, response.cookies)

    def test_authenticated_user_receives_signed_cookie(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("homepage"))

        self.assertIn(self.cookie_name, response.cookies)

        # Attach cookie to test client and verify get_signed_cookie unsigns JSON payload
        cookie_val = response.cookies[self.cookie_name].value
        self.client.cookies[self.cookie_name] = cookie_val

        req = self.client.get(reverse("homepage")).wsgi_request
        raw_data = req.get_signed_cookie(self.cookie_name, salt=self.salt)
        self.assertIsNotNone(raw_data)
        if raw_data is None:
            self.fail("raw_data cookie payload was unexpectedly None")

        data = json.loads(raw_data)

        self.assertEqual(data["uid"], self.user.pk)
        self.assertTrue(data["auth"])

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

    @patch("concordia.middleware.structured_logger.warning")
    def test_forged_or_invalid_signature_is_overwritten_and_logged(self, mock_logger):
        self.client.force_login(self.user)

        # Inject fake/spoofed signature cookie
        self.client.cookies[self.cookie_name] = "fake_signature_value"
        response = self.client.get(reverse("homepage"))

        self.assertIn(self.cookie_name, response.cookies)
        new_value = response.cookies[self.cookie_name].value
        self.assertNotEqual(new_value, "fake_signature_value")

        # Verify structured logger warning call
        mock_logger.assert_called_once()
        self.assertEqual(
            mock_logger.call_args.kwargs["event_code"],
            "cloudflare_auth_cookie_bad_signature",
        )

    @patch("concordia.middleware.structured_logger.warning")
    def test_corrupt_payload_is_overwritten_and_logged(self, mock_logger):
        self.client.force_login(self.user)

        # Use set_signed_cookie so signature validation passes in get_signed_cookie
        dummy_response = HttpResponse()
        dummy_response.set_signed_cookie(
            self.cookie_name,
            value="not_valid_json_payload",
            salt=self.salt,
        )
        corrupt_cookie = dummy_response.cookies[self.cookie_name].value

        self.client.cookies[self.cookie_name] = corrupt_cookie
        response = self.client.get(reverse("homepage"))

        self.assertIn(self.cookie_name, response.cookies)
        new_value = response.cookies[self.cookie_name].value
        self.assertNotEqual(new_value, corrupt_cookie)

        # Verify structured logger corrupt payload warning call
        mock_logger.assert_called_once()
        self.assertEqual(
            mock_logger.call_args.kwargs["event_code"],
            "cloudflare_auth_cookie_corrupt_payload",
        )
