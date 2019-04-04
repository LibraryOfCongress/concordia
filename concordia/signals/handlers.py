from asgiref.sync import AsyncToSync
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.dispatch import receiver
from django_registration.signals import user_registered

from ..models import Asset, Transcription, TranscriptionStatus
from ..tasks import calculate_difficulty_values
from .signals import reservation_obtained, reservation_released

ASSET_CHANNEL_LAYER = get_channel_layer()


@receiver(user_registered)
def add_user_to_newsletter(sender, user, request, **kwargs):
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
    new_status = TranscriptionStatus.IN_PROGRESS

    if instance.rejected:
        new_status = TranscriptionStatus.IN_PROGRESS
    elif instance.accepted:
        new_status = TranscriptionStatus.COMPLETED
    elif instance.submitted:
        new_status = TranscriptionStatus.SUBMITTED

    instance.asset.transcription_status = new_status
    instance.asset.full_clean()
    instance.asset.save()

    calculate_difficulty_values(Asset.objects.filter(pk=instance.asset.pk))


@receiver(post_save, sender=Asset)
def send_asset_update(*, instance, **kwargs):
    submitted_by = latest_trans = None

    latest_transcription = instance.transcription_set.order_by("-pk").first()
    if latest_transcription:
        submitted_by = latest_transcription.user.pk
        latest_trans = {
            "text": latest_transcription.text,
            "id": latest_transcription.pk,
        }

    AsyncToSync(ASSET_CHANNEL_LAYER.group_send)(
        "asset_updates",
        {
            "type": "asset_update",
            "asset_pk": instance.pk,
            "status": instance.transcription_status,
            "difficulty": instance.difficulty,
            "submitted_by": submitted_by,
            "latest_transcription": latest_trans,
        },
    )


@receiver(reservation_obtained)
def send_asset_reservation_obtained(sender, **kwargs):
    send_asset_reservation_message(
        sender=sender,
        message_type="asset_reservation_obtained",
        asset_pk=kwargs["asset_pk"],
        user_pk=kwargs["user_pk"],
    )


@receiver(reservation_released)
def send_asset_reservation_released(sender, **kwargs):
    send_asset_reservation_message(
        sender=sender,
        message_type="asset_reservation_released",
        asset_pk=kwargs["asset_pk"],
        user_pk=kwargs["user_pk"],
    )


def send_asset_reservation_message(*, sender, message_type, asset_pk, user_pk):
    AsyncToSync(ASSET_CHANNEL_LAYER.group_send)(
        "asset_updates",
        {"type": message_type, "asset_pk": asset_pk, "user_pk": user_pk},
    )
