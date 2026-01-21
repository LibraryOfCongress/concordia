from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.test import (
    RequestFactory,
    TransactionTestCase,
    override_settings,
)
from django.urls import reverse
from django.utils.timezone import now

from concordia.models import (
    AssetTranscriptionReservation,
    Transcription,
)
from concordia.signals.handlers import on_transcription_save
from concordia.tasks.reservations import (
    delete_old_tombstoned_reservations,
    expire_inactive_asset_reservations,
    tombstone_old_active_asset_reservations,
)
from concordia.utils import get_anonymous_user, get_or_create_reservation_token

from .utils import (
    CreateTestUsers,
    JSONAssertMixin,
    create_asset,
)


@override_settings(
    RATELIMIT_ENABLE=False, SESSION_ENGINE="django.contrib.sessions.backends.cache"
)
class AssetReservationViewTests(CreateTestUsers, JSONAssertMixin, TransactionTestCase):
    def test_asset_reservation(self):
        """
        Test the basic Asset reservation process
        """

        self.login_user()
        self._asset_reservation_test_payload(self.user.pk)

    def test_asset_reservation_anonymously(self):
        """
        Test the basic Asset reservation process as an anonymous user
        """

        anon_user = get_anonymous_user()
        self._asset_reservation_test_payload(anon_user.pk, anonymous=True)

    def _asset_reservation_test_payload(self, user_id, anonymous=False):
        asset = create_asset()

        # Acquire the reservation: 1 acquire
        # + 1 reservation check
        # + 1 logging if not anonymous
        # + 1 session if not anonymous and using a database session engine:
        expected_update_queries = 2
        if not anonymous:
            expected_update_queries += 1  # Added by django-structlog middleware
            if settings.SESSION_ENGINE.endswith("db"):
                expected_update_queries += 1  # Added by database session engine
            # We don't need to add an extra query for accessing request.user
            # because the django-structlog middleware will do that for non-anonymous
            expected_acquire_queries = expected_update_queries
        else:
            expected_acquire_queries = expected_update_queries + 1

        with self.assertNumQueries(expected_acquire_queries):
            resp = self.client.post(reverse("reserve-asset", args=(asset.pk,)))
        data = self.assertValidJSON(resp, expected_status=200)

        reservation = AssetTranscriptionReservation.objects.get()
        self.assertEqual(reservation.reservation_token, data["reservation_token"])
        self.assertEqual(reservation.asset, asset)

        # Confirm that an update did not change the pk when it updated the timestamp:

        with self.assertNumQueries(expected_update_queries):
            resp = self.client.post(reverse("reserve-asset", args=(asset.pk,)))
        data = self.assertValidJSON(resp, expected_status=200)
        self.assertEqual(1, AssetTranscriptionReservation.objects.count())
        updated_reservation = AssetTranscriptionReservation.objects.get()
        self.assertEqual(
            updated_reservation.reservation_token, data["reservation_token"]
        )
        self.assertEqual(updated_reservation.asset, asset)
        self.assertEqual(reservation.created_on, updated_reservation.created_on)
        self.assertLess(reservation.created_on, updated_reservation.updated_on)

        # Release the reservation now that we're done:
        # 1 release
        # + 1 logging if not anonymous
        # + 1 session if not anonymous and using a database
        expected_release_queries = 1
        if not anonymous:
            expected_release_queries += 1  # Added by django-structlog middleware
            if settings.SESSION_ENGINE.endswith("db"):
                expected_release_queries += 1

        with self.assertNumQueries(expected_release_queries):
            resp = self.client.post(
                reverse("reserve-asset", args=(asset.pk,)), data={"release": True}
            )
        data = self.assertValidJSON(resp, expected_status=200)
        self.assertEqual(
            updated_reservation.reservation_token, data["reservation_token"]
        )

        self.assertEqual(0, AssetTranscriptionReservation.objects.count())

    def test_asset_reservation_competition(self):
        """
        Confirm that two users cannot reserve the same asset at the same time
        """

        asset = create_asset()

        # We'll reserve the test asset as the anonymous user and then attempt
        # to edit it after logging in

        # 4 queries =
        # 1 expiry + 1 acquire + 2 get user ID + 2 get user profile from request
        with self.assertNumQueries(6):
            resp = self.client.post(reverse("reserve-asset", args=(asset.pk,)))
        self.assertEqual(200, resp.status_code)
        self.assertEqual(1, AssetTranscriptionReservation.objects.count())

        # Clear the login session so the reservation_token will be regenerated:
        self.client.logout()
        self.login_user()

        # 1 session check + 1 acquire + get user ID from request
        with self.assertNumQueries(3 if settings.SESSION_ENGINE.endswith("db") else 2):
            resp = self.client.post(reverse("reserve-asset", args=(asset.pk,)))
        self.assertEqual(409, resp.status_code)
        self.assertEqual(1, AssetTranscriptionReservation.objects.count())

    def test_asset_reservation_expiration(self):
        """
        Simulate an expired reservation which should not cause the request to fail
        """
        asset = create_asset()

        stale_reservation = AssetTranscriptionReservation(  # nosec
            asset=asset, reservation_token="stale"
        )
        stale_reservation.full_clean()
        stale_reservation.save()
        # Backdate the object as if it happened 31 minutes ago:
        old_timestamp = now() - timedelta(minutes=31)
        AssetTranscriptionReservation.objects.update(
            created_on=old_timestamp, updated_on=old_timestamp
        )

        expire_inactive_asset_reservations()

        self.login_user()

        # 1 reservation check + 1 acquire + 1 get user ID from request
        expected_queries = 3
        if settings.SESSION_ENGINE.endswith("db"):
            # 1 session check
            expected_queries += 1

        with self.assertNumQueries(expected_queries):
            resp = self.client.post(reverse("reserve-asset", args=(asset.pk,)))

        data = self.assertValidJSON(resp, expected_status=200)
        self.assertEqual(1, AssetTranscriptionReservation.objects.count())
        reservation = AssetTranscriptionReservation.objects.get()
        self.assertEqual(reservation.reservation_token, data["reservation_token"])

    def test_asset_reservation_tombstone(self):
        """
        Simulate a tombstoned reservation which should:
            - return 408 during the tombstone period
            - during the tombstone period, another user may
              obtain the reservation but the original user may not
        """
        asset = create_asset()
        self.login_user()
        request_factory = RequestFactory()
        request = request_factory.get("/")
        request.session = {}
        reservation_token = get_or_create_reservation_token(request)

        session = self.client.session
        session["reservation_token"] = reservation_token
        session.save()

        tombstone_reservation = AssetTranscriptionReservation(  # nosec
            asset=asset, reservation_token=reservation_token
        )
        tombstone_reservation.full_clean()
        tombstone_reservation.save()
        # Backdate the object as if it was created hours ago,
        # even if it was recently updated
        old_timestamp = now() - timedelta(
            hours=settings.TRANSCRIPTION_RESERVATION_TOMBSTONE_HOURS + 1
        )
        current_timestamp = now()
        AssetTranscriptionReservation.objects.update(
            created_on=old_timestamp, updated_on=current_timestamp
        )

        tombstone_old_active_asset_reservations()
        self.assertEqual(1, AssetTranscriptionReservation.objects.count())
        reservation = AssetTranscriptionReservation.objects.get()
        self.assertEqual(reservation.tombstoned, True)

        # 1 session check + 1 reservation check + 1 logging
        if settings.SESSION_ENGINE.endswith("db"):
            expected_queries = 3
        else:
            expected_queries = 2

        with self.assertNumQueries(expected_queries):
            resp = self.client.post(reverse("reserve-asset", args=(asset.pk,)))

        self.assertEqual(resp.status_code, 408)
        self.assertEqual(1, AssetTranscriptionReservation.objects.count())
        reservation = AssetTranscriptionReservation.objects.get()
        self.assertEqual(reservation.reservation_token, reservation_token)

        self.client.logout()

        # 1 reservation check + 1 acquire + 1 get user ID
        expected_queries = 3
        if settings.SESSION_ENGINE.endswith("db"):
            # + 1 session check
            expected_queries += 1

        User.objects.create_user(username="anonymous")
        with self.assertNumQueries(expected_queries):
            resp = self.client.post(reverse("reserve-asset", args=(asset.pk,)))

        self.assertValidJSON(resp, expected_status=200)
        self.assertEqual(2, AssetTranscriptionReservation.objects.count())

    def test_asset_reservation_tombstone_expiration(self):
        """
        Simulate a tombstoned reservation which should expire after
        the configured period of time, allowing the original user
        to reserve the asset again
        """
        asset = create_asset()
        self.login_user()
        request_factory = RequestFactory()
        request = request_factory.get("/")
        request.session = {}
        reservation_token = get_or_create_reservation_token(request)

        session = self.client.session
        session["reservation_token"] = reservation_token
        session.save()

        tombstone_reservation = AssetTranscriptionReservation(  # nosec
            asset=asset, reservation_token=reservation_token
        )
        tombstone_reservation.full_clean()
        tombstone_reservation.save()
        # Backdate the object as if it was created hours ago
        # and tombstoned hours ago
        old_timestamp = now() - timedelta(
            hours=settings.TRANSCRIPTION_RESERVATION_TOMBSTONE_HOURS
            + settings.TRANSCRIPTION_RESERVATION_TOMBSTONE_LENGTH_HOURS
            + 1
        )
        not_as_old_timestamp = now() - timedelta(
            hours=settings.TRANSCRIPTION_RESERVATION_TOMBSTONE_LENGTH_HOURS + 1
        )
        AssetTranscriptionReservation.objects.update(
            created_on=old_timestamp, updated_on=not_as_old_timestamp, tombstoned=True
        )

        delete_old_tombstoned_reservations()
        self.assertEqual(0, AssetTranscriptionReservation.objects.count())

        # 1 session check + 1 reservation check + 1 acquire + 1logging
        if settings.SESSION_ENGINE.endswith("db"):
            expected_queries = 4
        else:
            expected_queries = 3

        with self.assertNumQueries(expected_queries):
            resp = self.client.post(reverse("reserve-asset", args=(asset.pk,)))

        data = self.assertValidJSON(resp, expected_status=200)
        self.assertEqual(1, AssetTranscriptionReservation.objects.count())
        reservation = AssetTranscriptionReservation.objects.get()
        self.assertEqual(reservation.reservation_token, data["reservation_token"])
        self.assertEqual(reservation.tombstoned, False)

    def tearDown(self):
        # We'll test the signal handler separately
        post_save.connect(on_transcription_save, sender=Transcription)
