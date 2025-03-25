import logging
from time import time

from asgiref.sync import AsyncToSync
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib.auth import login as auth_login
from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.core.mail import EmailMultiAlternatives
from django.db.models import F, Q
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.template import loader
from django_registration.signals import user_activated, user_registered
from flags.state import flag_enabled

from ..models import (
    Asset,
    Transcription,
    TranscriptionStatus,
    UserProfile,
    UserProfileActivity,
)
from ..tasks import calculate_difficulty_values
from .signals import reservation_obtained, reservation_released

ASSET_CHANNEL_LAYER = get_channel_layer()

logger = logging.getLogger(__name__)


@receiver(user_logged_in)
def clear_reservation_token(sender, user, request, **kwargs):
    try:
        token = request.session["reservation_token"]
        del request.session["reservation_token"]
        request.session.save()
        logger.info("Clearing reservation token %s for %s on login", token, user)
    except KeyError:
        pass
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
    new_status = TranscriptionStatus.IN_PROGRESS

    if instance.rejected:
        new_status = TranscriptionStatus.IN_PROGRESS
    elif instance.accepted:
        new_status = TranscriptionStatus.COMPLETED
    elif instance.submitted:
        new_status = TranscriptionStatus.SUBMITTED

    asset = instance.asset
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
    send_asset_reservation_message(
        sender=sender,
        message_type="asset_reservation_released",
        asset_pk=kwargs["asset_pk"],
        reservation_token=kwargs["reservation_token"],
    )


def send_asset_reservation_message(
    *, sender, message_type, asset_pk, reservation_token
):
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
    if kwargs["created"]:
        user = instance.user
        attr_name = "transcribe_count"
    elif instance.reviewed_by:
        user = instance.reviewed_by
        attr_name = "review_count"
    else:
        user = None
        attr_name = None

    if user is not None and attr_name is not None:
        user_profile_activity, created = UserProfileActivity.objects.get_or_create(
            user=user,
            campaign=instance.asset.item.project.campaign,
        )
        profile, created = UserProfile.objects.get_or_create(user=user)
        if created:
            setattr(user_profile_activity, attr_name, 1)
            setattr(profile, attr_name, 1)
        else:
            setattr(user_profile_activity, attr_name, F(attr_name) + 1)
            setattr(profile, attr_name, F(attr_name) + 1)
        q = Q(transcription__user=user) | Q(transcription__reviewed_by=user)
        user_profile_activity.asset_count = (
            Asset.objects.filter(q)
            .filter(item__project__campaign=instance.asset.item.project.campaign)
            .distinct()
            .count()
        )
        user_profile_activity.save()
        profile.save()
