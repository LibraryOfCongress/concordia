from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
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

        # Inspect raw cookie string from response and decode using signing.loads
        cookie_val = response.cookies[self.cookie_name].value
        data = signing.loads(cookie_val, salt=self.salt)

        self.assertEqual(data["uid"], self.user.pk)
        self.assertTrue(data["auth"])

    @override_settings(CLOUDFLARE_AUTH_STATUS_COOKIE_NAME="_cf_rot_token")
    def test_configurable_cookie_name_from_settings(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("homepage"))

        self.assertIn("_cf_rot_token", response.cookies)
        self.assertNotIn("_cf_acc_status", response.cookies)

    def test_cookie_deleted_on_logout(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("homepage"))
        cookie_val = response.cookies[self.cookie_name].value

        # Attach active cookie to client and perform logout
        self.client.cookies[self.cookie_name] = cookie_val
        response = self.client.post(reverse("logout"))

        self.assertIn(self.cookie_name, response.cookies)
        self.assertEqual(response.cookies[self.cookie_name].value, "")

    def test_forged_or_invalid_signature_is_overwritten(self):
        self.client.force_login(self.user)

        # Inject fake/spoofed signature cookie
        self.client.cookies[self.cookie_name] = "fake_signature_value"
        response = self.client.get(reverse("homepage"))

        self.assertIn(self.cookie_name, response.cookies)
        new_value = response.cookies[self.cookie_name].value
        self.assertNotEqual(new_value, "fake_signature_value")
