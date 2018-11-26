from captcha.models import CaptchaStore
from django.test import TestCase, override_settings
from django.urls import reverse

from concordia.models import User

from .utils import JSONAssertMixin, create_asset

# Ratelimited views: save transcription,
# submit transcription, login, register,
# reserve asset


class RatelimitedViewTests(JSONAssertMixin, TestCase):
    def login_user(self):
        """
        Create a user and log the user in
        """

        # create user and login
        self.user = User.objects.create_user(
            username="tester", email="tester@example.com"
        )
        self.user.set_password("top_secret")
        self.user.save()

        self.client.login(username="tester", password="top_secret")

    def completeCaptcha(self, key=None):
        """Submit a CAPTCHA response using the provided challenge key"""

        if key is None:
            challenge_data = self.assertValidJSON(
                self.client.get(reverse("ajax-captcha")), expected_status=401
            )
            self.assertIn("key", challenge_data)
            self.assertIn("image", challenge_data)
            key = challenge_data["key"]

        self.assertValidJSON(
            self.client.post(
                reverse("ajax-captcha"),
                data={
                    "key": key,
                    "response": CaptchaStore.objects.get(hashkey=key).response,
                },
            )
        )

    @override_settings(RATELIMIT_ENABLE=True)
    def test_transcription_save_anon(self):
        # Anonymous users should only be able to save 1 per minute per IP
        asset = create_asset()

        # We're not testing the CAPTCHA here so we'll complete it:
        self.completeCaptcha()

        resp = self.client.post(
            reverse("save-transcription", args=(asset.pk,)), data={"text": "test"}
        )
        data = self.assertValidJSON(resp, expected_status=201)
        self.assertIn("submissionUrl", data)

        # This should be rate-limited
        resp = self.client.post(
            reverse("save-transcription", args=(asset.pk,)),
            data={"text": "test", "supersedes": asset.transcription_set.get().pk},
        )
        data = self.assertValidJSON(resp, expected_status=429)
        self.assertIn("exception", data)

    @override_settings(RATELIMIT_ENABLE=True)
    def test_transcription_save_auth(self):
        # Logged in users should be able to save without any rate limit
        self.login_user()
        asset = create_asset()

        resp = self.client.post(
            reverse("save-transcription", args=(asset.pk,)), data={"text": "test"}
        )
        data = self.assertValidJSON(resp, expected_status=201)
        self.assertIn("submissionUrl", data)

        # This should be rate-limited
        resp = self.client.post(
            reverse("save-transcription", args=(asset.pk,)),
            data={"text": "test", "supersedes": asset.transcription_set.get().pk},
        )
        data = self.assertValidJSON(resp, expected_status=201)
        self.assertIn("submissionUrl", data)
