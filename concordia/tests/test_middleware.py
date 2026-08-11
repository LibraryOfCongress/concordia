from django.contrib.auth import get_user_model
from django.core import signing
from django.test import TestCase
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
        self.cookie_name = CloudflareAuthStatusMiddleware.COOKIE_NAME
        self.salt = CloudflareAuthStatusMiddleware.SIGNING_SALT

    def test_anonymous_user_does_not_receive_cookie(self):
        response = self.client.get(reverse("homepage"))
        self.assertNotIn(self.cookie_name, response.cookies)

    def test_authenticated_user_receives_signed_cookie(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("homepage"))

        self.assertIn(self.cookie_name, response.cookies)
        cookie_value = response.cookies[self.cookie_name].value

        # Verify HMAC signature
        decoded = signing.loads(cookie_value, salt=self.salt)
        self.assertEqual(decoded["uid"], self.user.pk)
        self.assertTrue(decoded["auth"])

    def test_cookie_deleted_on_logout(self):
        self.client.force_login(self.user)
        # Establish cookie on client
        response = self.client.get(reverse("homepage"))
        cookie_value = response.cookies[self.cookie_name].value

        # Set cookie in next request and logout
        self.client.cookies[self.cookie_name] = cookie_value
        response = self.client.post(reverse("logout"))

        # Middleware should delete cookie for anonymous/logged-out state
        self.assertIn(self.cookie_name, response.cookies)
        self.assertEqual(response.cookies[self.cookie_name].value, "")

    def test_tampered_cookie_is_overwritten_for_authenticated_user(self):
        self.client.force_login(self.user)

        # Inject forged cookie
        self.client.cookies[self.cookie_name] = "invalid_tampered_hmac_signature"
        response = self.client.get(reverse("homepage"))

        # Middleware detects bad signature and overwrites with valid token
        self.assertIn(self.cookie_name, response.cookies)
        new_cookie_value = response.cookies[self.cookie_name].value
        self.assertNotEqual(new_cookie_value, "invalid_tampered_hmac_signature")

        decoded = signing.loads(new_cookie_value, salt=self.salt)
        self.assertEqual(decoded["uid"], self.user.pk)
