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
