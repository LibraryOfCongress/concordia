from unittest import mock

from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_logged_in
from django.core import mail
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from django_registration.signals import user_activated, user_registered
from structlog.contextvars import bind_contextvars, clear_contextvars

from concordia.models import TranscriptionStatus
from concordia.signals.handlers import add_request_id_to_response

from .utils import CreateTestUsers, create_asset, create_transcription


class TestSignalHandlers(CreateTestUsers, TestCase):
    def setUp(self):
        self.user = self.create_test_user()
        self.asset = create_asset()
        self.request_factory = RequestFactory()

    def test_clear_reservation_token(self):
        self.login_user()
        response = self.client.get(reverse("redirect-to-next-transcribable-asset"))
        self.assertIsNotNone(self.client.session.get("reservation_token"))
        user_logged_in.send(
            sender=self.__class__, user=self.user, request=response.wsgi_request
        )
        self.assertIsNone(self.client.session.get("reservation_token"))

    def test_user_successfully_activated(self):
        with mock.patch("concordia.signals.handlers.flag_enabled") as flag_mock:
            flag_mock.return_value = True
            response = self.client.get("/")
            request = response.wsgi_request
            user_activated.send(sender=self.__class__, user=self.user, request=request)
            self.assertTrue(request.user.is_authenticated)
            self.assertEqual(len(mail.outbox), 1)

    def test_user_successfully_activated_no_request(self):
        with mock.patch("concordia.signals.handlers.flag_enabled") as flag_mock:
            flag_mock.return_value = True
            user_activated.send(sender=self.__class__, user=self.user, request=None)
            self.assertEqual(len(mail.outbox), 1)

    def test_user_successfully_activated_no_welcome_email(self):
        with mock.patch("concordia.signals.handlers.flag_enabled") as flag_mock:
            flag_mock.return_value = False
            response = self.client.get("/")
            request = response.wsgi_request
            user_activated.send(sender=self.__class__, user=self.user, request=request)
            self.assertTrue(request.user.is_authenticated)
            self.assertEqual(len(mail.outbox), 0)

    def test_add_user_to_newsletter(self):
        self.login_user()
        response = self.client.post("/")
        user_registered.send(
            sender=self.__class__, user=self.user, request=response.wsgi_request
        )
        self.assertNotIn(
            self.user,
            Group.objects.get(name=settings.NEWSLETTER_GROUP_NAME).user_set.all(),
        )

        response = self.client.post("/", data={"newsletterOptIn": True})
        user_registered.send(
            sender=self.__class__, user=self.user, request=response.wsgi_request
        )
        self.assertIn(
            self.user,
            Group.objects.get(name=settings.NEWSLETTER_GROUP_NAME).user_set.all(),
        )


class UpdateAssetStatusSignalTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.user1 = self.create_user("user-1")
        self.user2 = self.create_user("user-2")
        self.asset = create_asset()

    def test_accepted_transcription_sets_completed_status(self):
        create_transcription(asset=self.asset, user=self.user1, accepted=timezone.now())

        self.asset.refresh_from_db()
        self.assertEqual(self.asset.transcription_status, TranscriptionStatus.COMPLETED)

    def test_submitted_transcription_sets_submitted_status(self):
        create_transcription(
            asset=self.asset, user=self.user1, submitted=timezone.now()
        )

        self.asset.refresh_from_db()
        self.assertEqual(self.asset.transcription_status, TranscriptionStatus.SUBMITTED)

    def test_rejected_transcription_sets_in_progress_status(self):
        create_transcription(asset=self.asset, user=self.user1, rejected=timezone.now())

        self.asset.refresh_from_db()
        self.assertEqual(
            self.asset.transcription_status, TranscriptionStatus.IN_PROGRESS
        )

    def test_default_transcription_sets_in_progress_status(self):
        create_transcription(asset=self.asset, user=self.user1)

        self.asset.refresh_from_db()
        self.assertEqual(
            self.asset.transcription_status, TranscriptionStatus.IN_PROGRESS
        )

    def test_outdated_transcription_does_not_update_status(self):
        t1 = create_transcription(
            asset=self.asset, user=self.user1, submitted=timezone.now()
        )
        create_transcription(asset=self.asset, user=self.user2, accepted=timezone.now())

        # Now "re-save" the older one to trigger the signal
        # Expecting this save to trigger the warning logger since t1 is no longer latest
        with self.assertLogs("concordia.signals.handlers", level="WARNING") as log_cm:
            t1.rejected = timezone.now()
            t1.save()

        self.asset.refresh_from_db()
        # Status should remain COMPLETED due to latest transcription not being t1
        self.assertEqual(self.asset.transcription_status, TranscriptionStatus.COMPLETED)

        # Verify that a warning was indeed logged about outdated transcription
        self.assertTrue(
            any("An older transcription" in message for message in log_cm.output)
        )
        self.assertTrue(any(str(t1.id) in message for message in log_cm.output))
        self.assertTrue(any(str(self.asset.id) in message for message in log_cm.output))

    @mock.patch("concordia.signals.handlers.remove_next_asset_objects")
    @mock.patch("concordia.signals.handlers.calculate_difficulty_values")
    def test_tasks_called_on_latest_transcription(self, mock_calc, mock_remove):
        create_transcription(asset=self.asset, user=self.user1, accepted=timezone.now())

        mock_remove.assert_called_once_with(self.asset.id)
        mock_calc.assert_called_once()
        args, _ = mock_calc.call_args
        self.assertEqual(list(args[0].values_list("pk", flat=True)), [self.asset.pk])


class RequestIDHeaderTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        clear_contextvars()
        bind_contextvars(request_id="test-id-123")

    def tearDown(self):
        clear_contextvars()

    def make_response(self, cache_control_header=None):
        response = HttpResponse("ok")
        if cache_control_header:
            response["Cache-Control"] = cache_control_header
        return response

    @mock.patch(
        "structlog.contextvars.get_merged_contextvars",
        return_value={"request_id": "test-id-123"},
    )
    def test_adds_header_when_no_cache_control(self, mock_contextvars):
        response = self.make_response()
        add_request_id_to_response(response=response, logger=None)
        self.assertEqual(response["X-Request-ID"], "test-id-123")

    @mock.patch(
        "structlog.contextvars.get_merged_contextvars",
        return_value={"request_id": "test-id-123"},
    )
    def test_adds_header_when_private(self, mock_contextvars):
        response = self.make_response("private, no-store")
        add_request_id_to_response(response=response, logger=None)
        self.assertEqual(response["X-Request-ID"], "test-id-123")

    @mock.patch(
        "structlog.contextvars.get_merged_contextvars",
        return_value={"request_id": "test-id-123"},
    )
    def test_skips_header_when_public_with_max_age(self, mock_contextvars):
        response = self.make_response("public, max-age=600")
        add_request_id_to_response(response=response, logger=None)
        self.assertNotIn("X-Request-ID", response)

    @mock.patch(
        "structlog.contextvars.get_merged_contextvars",
        return_value={"request_id": "test-id-123"},
    )
    def test_adds_header_when_no_store_present(self, mock_contextvars):
        response = self.make_response("public, no-store")
        add_request_id_to_response(response=response, logger=None)
        self.assertEqual(response["X-Request-ID"], "test-id-123")
