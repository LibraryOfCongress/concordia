import sys
from unittest.mock import patch

from django import forms
from django.db.models.signals import post_save
from django.test import (
    TransactionTestCase,
    override_settings,
)
from django.urls import reverse

from concordia.models import (
    Transcription,
)
from concordia.signals.handlers import on_transcription_save

from .utils import (
    CreateTestUsers,
    JSONAssertMixin,
    create_asset,
)


@override_settings(
    RATELIMIT_ENABLE=False, SESSION_ENGINE="django.contrib.sessions.backends.cache"
)
class SaveTranscriptionViewTests(CreateTestUsers, JSONAssertMixin, TransactionTestCase):
    def setUp(self):
        self.asset = create_asset()

    def test_turnstile_validation_fails(self):
        # Test when Turnstile validation failes
        with patch("concordia.turnstile.fields.TurnstileField.validate") as mock:
            mock.side_effect = forms.ValidationError(
                "Testing error", code="invalid_turnstile"
            )
            resp = self.client.post(
                reverse("save-transcription", args=(self.asset.pk,)),
                data={"text": "test"},
            )
            data = self.assertValidJSON(resp, expected_status=401)
            self.assertIn("error", data)

    def test_initial_save_success(self):
        with patch(
            "concordia.turnstile.fields.TurnstileField.validate", return_value=True
        ):
            resp = self.client.post(
                reverse("save-transcription", args=(self.asset.pk,)),
                data={"text": "test"},
            )
        data = self.assertValidJSON(resp, expected_status=201)
        self.assertIn("submissionUrl", data)

    def test_duplicate_without_supersedes_conflict(self):
        with patch(
            "concordia.turnstile.fields.TurnstileField.validate", return_value=True
        ):
            self.client.post(
                reverse("save-transcription", args=(self.asset.pk,)),
                data={"text": "test"},
            )
            # Test attempts to create a second transcription without marking that it
            # supersedes the previous one:
            resp = self.client.post(
                reverse("save-transcription", args=(self.asset.pk,)),
                data={"text": "test"},
            )
        data = self.assertValidJSON(resp, expected_status=409)
        self.assertIn("error", data)

    def test_save_with_url_error(self):
        with patch(
            "concordia.turnstile.fields.TurnstileField.validate", return_value=True
        ):
            self.client.post(
                reverse("save-transcription", args=(self.asset.pk,)),
                data={"text": "test"},
            )
            # If a transcription contains a URL, it should return an error
            resp = self.client.post(
                reverse("save-transcription", args=(self.asset.pk,)),
                data={
                    "text": "http://example.com",
                    "supersedes": self.asset.transcription_set.get().pk,
                },
            )
        data = self.assertValidJSON(resp, expected_status=400)
        self.assertIn("error", data)

    def test_unacceptable_characters_are_removed_on_save(self):
        with patch(
            "concordia.turnstile.fields.TurnstileField.validate", return_value=True
        ):
            bad_text = "He\u200bllo\tWorld\xa0\u3000\u2003!\nBad\x00Char\x1fHere\u200b"
            resp = self.client.post(
                reverse("save-transcription", args=(self.asset.pk,)),
                data={"text": bad_text},
            )
        data = self.assertValidJSON(resp, expected_status=201)
        self.assertIn("submissionUrl", data)
        t = self.asset.transcription_set.get()
        self.assertEqual(t.text, "Hello\tWorld\xa0\u3000\u2003!\nBadCharHere")

    def test_unacceptable_characters_are_removed_when_superseding(self):
        with patch(
            "concordia.turnstile.fields.TurnstileField.validate", return_value=True
        ):
            self.client.post(
                reverse("save-transcription", args=(self.asset.pk,)),
                data={"text": "first"},
            )
            bad_text = "b\u200bad\x00"
            resp = self.client.post(
                reverse("save-transcription", args=(self.asset.pk,)),
                data={
                    "text": bad_text,
                    "supersedes": self.asset.transcription_set.get().pk,
                },
            )
        data = self.assertValidJSON(resp, expected_status=201)
        self.assertIn("submissionUrl", data)
        new_t = self.asset.transcription_set.order_by("pk").last()
        self.assertEqual(new_t.text, "bad")

    def test_save_with_supersedes_success(self):
        with patch(
            "concordia.turnstile.fields.TurnstileField.validate", return_value=True
        ):
            self.client.post(
                reverse("save-transcription", args=(self.asset.pk,)),
                data={"text": "test"},
            )
            # Test that it correctly works when supersedes is set
            resp = self.client.post(
                reverse("save-transcription", args=(self.asset.pk,)),
                data={
                    "text": "test",
                    "supersedes": self.asset.transcription_set.get().pk,
                },
            )
        data = self.assertValidJSON(resp, expected_status=201)
        self.assertIn("submissionUrl", data)

    def test_supersedes_sets_ocr_originated_when_previous_was_ocr_originated(self):
        with patch(
            "concordia.turnstile.fields.TurnstileField.validate", return_value=True
        ):
            self.client.post(
                reverse("save-transcription", args=(self.asset.pk,)),
                data={"text": "test"},
            )
            # Test that it correctly works when supersedes is set and confirm
            # ocr_originaed is properly set
            transcription = self.asset.transcription_set.order_by("pk").last()
            transcription.ocr_originated = True
            transcription.save()
            resp = self.client.post(
                reverse("save-transcription", args=(self.asset.pk,)),
                data={
                    "text": "test",
                    "supersedes": self.asset.transcription_set.order_by("pk").last().pk,
                },
            )
        data = self.assertValidJSON(resp, expected_status=201)
        self.assertIn("submissionUrl", data)
        new_transcription = self.asset.transcription_set.order_by("pk").last()
        self.assertTrue(new_transcription.ocr_originated)

    def test_supersede_already_superseded_conflict(self):
        with patch(
            "concordia.turnstile.fields.TurnstileField.validate", return_value=True
        ):
            first_resp = self.client.post(
                reverse("save-transcription", args=(self.asset.pk,)),
                data={"text": "test"},
            )
            self.assertValidJSON(first_resp, expected_status=201)
            first_pk = self.asset.transcription_set.order_by("pk").first().pk

            self.client.post(
                reverse("save-transcription", args=(self.asset.pk,)),
                data={"text": "test 2", "supersedes": first_pk},
            )

            # We should see an error if you attempt to supersede a transcription
            # which has already been superseded:
            resp = self.client.post(
                reverse("save-transcription", args=(self.asset.pk,)),
                data={
                    "text": "test",
                    "supersedes": self.asset.transcription_set.order_by("pk")
                    .first()
                    .pk,
                },
            )
        data = self.assertValidJSON(resp, expected_status=409)
        self.assertIn("error", data)

    def test_supersede_nonexistent_returns_400(self):
        with patch(
            "concordia.turnstile.fields.TurnstileField.validate", return_value=True
        ):
            # We should get an error if you attempt to supersede a transcription
            # that doesn't exist
            resp = self.client.post(
                reverse("save-transcription", args=(self.asset.pk,)),
                data={
                    "text": "test",
                    "supersedes": sys.maxsize,
                },
            )
        data = self.assertValidJSON(resp, expected_status=400)
        self.assertIn("error", data)

    def test_supersede_invalid_pk_returns_400(self):
        with patch(
            "concordia.turnstile.fields.TurnstileField.validate", return_value=True
        ):
            # We should get an error if you attempt to supersede with
            # with a pk that is invalid (i.e., a string instead of int)
            resp = self.client.post(
                reverse("save-transcription", args=(self.asset.pk,)),
                data={
                    "text": "test",
                    "supersedes": "bad-pk",
                },
            )
        data = self.assertValidJSON(resp, expected_status=400)
        self.assertIn("error", data)

    def test_logged_in_user_can_take_over_from_anonymous(self):
        with patch(
            "concordia.turnstile.fields.TurnstileField.validate", return_value=True
        ):
            anon_resp = self.client.post(
                reverse("save-transcription", args=(self.asset.pk,)),
                data={"text": "test"},
            )
            self.assertValidJSON(anon_resp, expected_status=201)

            # A logged in user can take over from an anonymous user:
            self.login_user()
            resp = self.client.post(
                reverse("save-transcription", args=(self.asset.pk,)),
                data={
                    "text": "test",
                    "supersedes": self.asset.transcription_set.order_by("pk").last().pk,
                },
            )
        data = self.assertValidJSON(resp, expected_status=201)
        self.assertIn("submissionUrl", data)

    def tearDown(self):
        # We'll test the signal handler separately
        post_save.connect(on_transcription_save, sender=Transcription)
