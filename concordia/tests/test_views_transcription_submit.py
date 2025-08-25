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
from concordia.utils import get_anonymous_user

from .utils import (
    CreateTestUsers,
    JSONAssertMixin,
    create_asset,
)


@override_settings(
    RATELIMIT_ENABLE=False, SESSION_ENGINE="django.contrib.sessions.backends.cache"
)
class SubmitTranscriptionViewTests(
    CreateTestUsers, JSONAssertMixin, TransactionTestCase
):
    def test_anonymous_transcription_submission(self):
        asset = create_asset()
        anon = get_anonymous_user()

        transcription = Transcription(asset=asset, user=anon, text="previous entry")
        transcription.full_clean()
        transcription.save()

        with patch("concordia.turnstile.fields.TurnstileField.validate") as mock:
            mock.side_effect = forms.ValidationError(
                "Testing error", code="invalid_turnstile"
            )
            resp = self.client.post(
                reverse("submit-transcription", args=(transcription.pk,))
            )
        data = self.assertValidJSON(resp, expected_status=401)
        self.assertIn("error", data)

        self.assertFalse(Transcription.objects.filter(submitted__isnull=False).exists())

        with patch(
            "concordia.turnstile.fields.TurnstileField.validate", return_value=True
        ):
            self.client.post(
                reverse("submit-transcription", args=(transcription.pk,)),
            )
            self.assertTrue(
                Transcription.objects.filter(submitted__isnull=False).exists()
            )

    def test_transcription_submission(self):
        asset = create_asset()

        with patch(
            "concordia.turnstile.fields.TurnstileField.validate", return_value=True
        ):
            resp = self.client.post(
                reverse("save-transcription", args=(asset.pk,)), data={"text": "test"}
            )
        data = self.assertValidJSON(resp, expected_status=201)

        transcription = Transcription.objects.get()
        self.assertIsNone(transcription.submitted)

        with patch(
            "concordia.turnstile.fields.TurnstileField.validate", return_value=True
        ):
            resp = self.client.post(
                reverse("submit-transcription", args=(transcription.pk,))
            )
        data = self.assertValidJSON(resp, expected_status=200)
        self.assertIn("id", data)
        self.assertEqual(data["id"], transcription.pk)

        transcription = Transcription.objects.get()
        self.assertTrue(transcription.submitted)

    def test_stale_transcription_submission(self):
        asset = create_asset()

        anon = get_anonymous_user()

        t1 = Transcription(asset=asset, user=anon, text="test")
        t1.full_clean()
        t1.save()

        t2 = Transcription(asset=asset, user=anon, text="test", supersedes=t1)
        t2.full_clean()
        t2.save()

        with patch(
            "concordia.turnstile.fields.TurnstileField.validate", return_value=True
        ):
            resp = self.client.post(reverse("submit-transcription", args=(t1.pk,)))
            data = self.assertValidJSON(resp, expected_status=400)
            self.assertIn("error", data)

    def tearDown(self):
        # We'll test the signal handler separately
        post_save.connect(on_transcription_save, sender=Transcription)
