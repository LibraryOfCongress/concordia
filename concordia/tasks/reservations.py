import datetime
from logging import getLogger

from django.conf import settings
from django.utils import timezone

from concordia.logging import ConcordiaLogger
from concordia.models import AssetTranscriptionReservation
from concordia.signals.signals import reservation_released

from ..celery import app as celery_app

logger = getLogger(__name__)
structured_logger = ConcordiaLogger.get_logger(__name__)


@celery_app.task
def expire_inactive_asset_reservations():
    """
    Release and delete stale asset transcription reservations.

    This task identifies reservations which have not been updated within a grace
    period defined as twice ``TRANSCRIPTION_RESERVATION_SECONDS`` and:

    * Emits the ``reservation_released`` signal for each expired reservation so
      any listeners can react (for example, by making the asset available again).
    * Deletes the expired reservation records from the database.

    This is intended to be run periodically (for example via Celery beat) to
    ensure that abandoned reservations do not block other users from working on
    assets.
    """
    timestamp = timezone.now()

    # Clear old reservations, with a grace period:
    cutoff = timestamp - (
        datetime.timedelta(seconds=2 * settings.TRANSCRIPTION_RESERVATION_SECONDS)
    )

    logger.debug("Clearing reservations with last reserve time older than %s", cutoff)
    expired_reservations = AssetTranscriptionReservation.objects.filter(
        updated_on__lt=cutoff, tombstoned__in=(None, False)
    )

    for reservation in expired_reservations:
        logger.debug("Expired reservation with token %s", reservation.reservation_token)
        reservation_released.send(
            sender="reserve_asset",
            asset_pk=reservation.asset.pk,
            reservation_token=reservation.reservation_token,
        )
        reservation.delete()


@celery_app.task
def tombstone_old_active_asset_reservations():
    """
    Mark very old active reservations as tombstoned.

    This task finds asset transcription reservations whose ``created_on`` is
    older than ``TRANSCRIPTION_RESERVATION_TOMBSTONE_HOURS`` and that are not
    already tombstoned. Each matching reservation is marked with
    ``tombstoned=True`` and saved.

    Tombstoning is a soft-deactivation step that prevents further use of
    obsolete reservations while still retaining a short history for debugging
    or analytics before final deletion.
    """
    timestamp = timezone.now()

    cutoff = timestamp - (
        datetime.timedelta(hours=settings.TRANSCRIPTION_RESERVATION_TOMBSTONE_HOURS)
    )

    old_reservations = AssetTranscriptionReservation.objects.filter(
        created_on__lt=cutoff, tombstoned__in=(None, False)
    )
    for reservation in old_reservations:
        logger.debug("Tombstoning reservation %s ", reservation.reservation_token)
        reservation.tombstoned = True
        reservation.save()


@celery_app.task
def delete_old_tombstoned_reservations():
    """
    Permanently delete tombstoned reservations after a retention period.

    This task finds asset transcription reservations which:

    * Have ``tombstoned=True``, and
    * Have not been updated within
      ``TRANSCRIPTION_RESERVATION_TOMBSTONE_LENGTH_HOURS``.

    Each matching reservation is deleted from the database. This provides a
    final cleanup step after tombstoning so reservation records do not linger
    indefinitely.
    """
    timestamp = timezone.now()

    cutoff = timestamp - (
        datetime.timedelta(
            hours=settings.TRANSCRIPTION_RESERVATION_TOMBSTONE_LENGTH_HOURS
        )
    )

    old_reservations = AssetTranscriptionReservation.objects.filter(
        tombstoned__exact=True, updated_on__lt=cutoff
    )
    for reservation in old_reservations:
        logger.debug(
            "Deleting old tombstoned reservation %s", reservation.reservation_token
        )
        reservation.delete()
