import logging
from time import time

import structlog
from asgiref.sync import AsyncToSync
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib.auth import login as auth_login
from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.core.mail import EmailMultiAlternatives
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.template import loader
from django_registration.signals import user_activated, user_registered
from django_structlog import signals
from flags.state import flag_enabled

from concordia.logging import ConcordiaLogger
from concordia.models import (
    Asset,
    Transcription,
    TranscriptionStatus,
    UserProfile,
)
from concordia.tasks import calculate_difficulty_values, update_useractivity_cache
from concordia.utils.next_asset import remove_next_asset_objects

from .signals import reservation_obtained, reservation_released

ASSET_CHANNEL_LAYER = get_channel_layer()

logger = logging.getLogger(__name__)
structured_logger = ConcordiaLogger.get_logger(__name__)


@receiver(user_logged_in)
def clear_reservation_token(sender, user, request, **kwargs):
    try:
        token = request.session["reservation_token"]
        del request.session["reservation_token"]
        request.session.save()
        logger.info("Clearing reservation token %s for %s on login", token, user)
        structured_logger.info(
            "Reservation token cleared on login.",
            event_code="reservation_token_cleared",
            reservation_token=token,
            user=user,
        )
    except KeyError:
        structured_logger.debug(
            "No reservation token found to clear on login.",
            event_code="reservation_token_absent_on_login",
            user=user,
        )

    logger.info("Successful user login with username %s", user)


@receiver(user_login_failed)
def handle_user_login_failed(sender, credentials, request, **kwargs):
    logger.warning("Failed user login with username %s", credentials["username"])


@receiver(user_activated)
def user_successfully_activated(sender, user, request, **kwargs):
    logger.info("Received user activation signal for %s", user.username)

    # Log the user in, if this isn't the result of a password reset
    # The password reset form automatically logs the user in and activates.
    # But when it does so, it sends None for the request.
    # So when the user activates without resetting the password, the behavior
    # should be the same - the user should be automatically logged in.
    if request:
        auth_login(request, user)

    if flag_enabled("SEND_WELCOME_EMAIL"):
        text_body_template = loader.get_template("emails/welcome_email_body.txt")
        text_body_message = text_body_template.render()

        html_body_template = loader.get_template("emails/welcome_email_body.html")
        html_body_message = html_body_template.render()

        subject_template = loader.get_template("emails/welcome_email_subject.txt")
        subject_message = subject_template.render()

        # Send welcome email
        message = EmailMultiAlternatives(
            subject=subject_message.rstrip(),
            body=text_body_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
            reply_to=[settings.DEFAULT_FROM_EMAIL],
        )
        message.attach_alternative(html_body_message, "text/html")
        message.send()


@receiver(user_registered)
def add_user_to_newsletter(sender, user, request, **kwargs):
    # If the user checked the newsletter checkbox,
    # add them to the Newsletter group
    if (
        request.POST
        and "newsletterOptIn" in request.POST
        and request.POST["newsletterOptIn"]
    ):
        newsletter_group = Group.objects.get(name=settings.NEWSLETTER_GROUP_NAME)
        newsletter_group.user_set.add(user)
        newsletter_group.save()


@receiver(post_save, sender=Transcription)
def update_asset_status(sender, *, instance, **kwargs):
    logger.info("update_asset_status for %s", instance.id)

    asset = instance.asset

    new_status = TranscriptionStatus.IN_PROGRESS

    if instance.rejected:
        new_status = TranscriptionStatus.IN_PROGRESS
    elif instance.accepted:
        new_status = TranscriptionStatus.COMPLETED
    elif instance.submitted:
        new_status = TranscriptionStatus.SUBMITTED

    # Before we do anything, we need to make sure this
    # is the latest transcription for the asset.
    current_latest_transcription = asset.latest_transcription()
    if instance != current_latest_transcription:
        # A transcription lower down in the asset's history has been updated.
        # This shouldn't happen outside of extraordinary circumstances.
        # We'll log this occurrence then skip the rest of the signal because
        # we don't want to change the asset's status since changing an older
        # transcription doesn't logically affect the status or anything else
        logger.warning(
            "An older transcription (%s) was updated for asset %s (%s). This "
            "would have updated the status to %s, but this was prevented and "
            "the status remained %s. The current latest_transcription is %s. "
            "The sender was %s.",
            instance.id,
            asset,
            asset.id,
            new_status,
            asset.transcription_status,
            current_latest_transcription,
            sender,
        )
        return

    logger.info(
        "Updating asset status for %s (%s) from %s to %s",
        asset,
        asset.id,
        asset.transcription_status,
        new_status,
    )

    asset.transcription_status = new_status
    asset.full_clean()
    asset.save()

    logger.info("Status for %s (%s) updated", asset, asset.id)

    remove_next_asset_objects(asset.id)

    calculate_difficulty_values(Asset.objects.filter(pk=asset.pk))


@receiver(post_save, sender=Asset)
def send_asset_update(*, instance, **kwargs):
    latest_trans = None

    latest_transcription = instance.transcription_set.order_by("-pk").first()
    if latest_transcription:
        latest_trans = {
            "text": latest_transcription.text,
            "id": latest_transcription.pk,
            "submitted_by": latest_transcription.user.pk,
        }

    AsyncToSync(ASSET_CHANNEL_LAYER.group_send)(
        "asset_updates",
        {
            "type": "asset_update",
            "asset_pk": instance.pk,
            "status": instance.transcription_status,
            "difficulty": instance.difficulty,
            "latest_transcription": latest_trans,
        },
    )


@receiver(reservation_obtained)
def send_asset_reservation_obtained(sender, **kwargs):
    logger.info(
        "Reservation obtained by %s for asset %s with token %s",
        sender,
        kwargs["asset_pk"],
        kwargs["reservation_token"],
    )

    structured_logger.info(
        "Asset reservation obtained.",
        event_code="asset_reservation_obtained",
        asset_pk=kwargs["asset_pk"],
        reservation_token=kwargs["reservation_token"],
        sender=sender,
    )

    send_asset_reservation_message(
        sender=sender,
        message_type="asset_reservation_obtained",
        asset_pk=kwargs["asset_pk"],
        reservation_token=kwargs["reservation_token"],
    )


@receiver(reservation_released)
def send_asset_reservation_released(sender, **kwargs):
    logger.info(
        "Reservation released by %s for asset %s with token %s",
        sender,
        kwargs["asset_pk"],
        kwargs["reservation_token"],
    )
    structured_logger.info(
        "Asset reservation released.",
        event_code="asset_reservation_released",
        asset_pk=kwargs["asset_pk"],
        reservation_token=kwargs["reservation_token"],
        sender=sender,
    )
    send_asset_reservation_message(
        sender=sender,
        message_type="asset_reservation_released",
        asset_pk=kwargs["asset_pk"],
        reservation_token=kwargs["reservation_token"],
    )


def send_asset_reservation_message(
    *, sender, message_type, asset_pk, reservation_token
):
    structured_logger.debug(
        "Dispatching reservation message to channel layer.",
        event_code="asset_reservation_channel_dispatch",
        message_type=message_type,
        asset_pk=asset_pk,
        reservation_token=reservation_token,
        sender=sender,
    )
    AsyncToSync(ASSET_CHANNEL_LAYER.group_send)(
        "asset_updates",
        {
            "type": message_type,
            "asset_pk": asset_pk,
            "reservation_token": reservation_token,
            "sent": time(),
        },
    )


@receiver(post_delete, sender=Asset)
def remove_file_from_s3(sender, instance, using, **kwargs):
    instance.storage_image.delete(save=False)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, *args, **kwargs):
    if not hasattr(instance, "profile"):
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=Transcription)
def on_transcription_save(sender, instance, **kwargs):
    r"""
    :param instance:
        the transcription being saved
    """
    if kwargs.get("created", False):
        user = instance.user
        attr_name = "transcribe"
    elif instance.reviewed_by:
        user = instance.reviewed_by
        attr_name = "review"
    else:
        user = None
        attr_name = None

    if user is not None and attr_name is not None and user.username != "anonymous":
        structured_logger.info(
            "Transcription saved; updating user activity cache.",
            event_code="transcription_useractivity_triggered",
            transcription=instance,
            user=user,
            activity_type=attr_name,
            campaign=instance.asset.item.project.campaign,
        )
        update_useractivity_cache.delay(
            user.id,
            instance.asset.item.project.campaign.id,
            attr_name,
        )


@receiver(signals.update_failure_response)
@receiver(signals.bind_extra_request_finished_metadata)
def add_request_id_to_response(response, logger, **kwargs):
    cache_control = response.get("Cache-Control", "").lower()

    is_public = "public" in cache_control or "max-age" in cache_control
    is_private = (
        "private" in cache_control
        or "no-store" in cache_control
        or "no-cache" in cache_control
    )

    if is_public and not is_private:
        # Don't add header to potentially cacheable responses
        # to avoid the cache storing a bad request_id
        return

    context = structlog.contextvars.get_merged_contextvars(logger)
    response["X-Request-ID"] = context["request_id"]
