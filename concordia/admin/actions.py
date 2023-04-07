import uuid
from logging import getLogger

from django.contrib import admin, messages
from django.utils.timezone import now

from ..models import Asset, Transcription, TranscriptionStatus

logger = getLogger(__name__)


@admin.action(permissions=["change"], description="Anonymize and disable user accounts")
def anonymize_action(modeladmin, request, queryset):
    count = queryset.count()
    for user_account in queryset:
        user_account.username = "Anonymized %s" % uuid.uuid4()
        user_account.email = ""
        user_account.set_unusable_password()
        user_account.is_active = False
        user_account.save()

    messages.info(request, f"Anonymized and disabled {count} user accounts")


@admin.action(permissions=["change"], description="Publish selected items and assets")
def publish_item_action(modeladmin, request, queryset):
    """
    Mark all of the selected items and their related assets as published
    """

    count = queryset.filter(published=False).update(published=True)
    asset_count = Asset.objects.filter(item__in=queryset, published=False).update(
        published=True
    )

    messages.info(request, f"Published {count} items and {asset_count} assets")


@admin.action(permissions=["change"], description="Unpublish selected items and assets")
def unpublish_item_action(modeladmin, request, queryset):
    """
    Mark all of the selected items and their related assets as unpublished
    """

    count = queryset.filter(published=True).update(published=False)
    asset_count = Asset.objects.filter(item__in=queryset, published=True).update(
        published=False
    )

    messages.info(request, f"Unpublished {count} items and {asset_count} assets")


@admin.action(permissions=["change"], description="Publish selected")
def publish_action(modeladmin, request, queryset):
    """
    Mark all of the selected objects as published
    """

    count = queryset.filter(published=False).update(published=True)
    messages.info(request, f"Published {count} objects")


@admin.action(permissions=["change"], description="Unpublish selected")
def unpublish_action(modeladmin, request, queryset):
    """
    Mark all of the selected objects as unpublished
    """

    count = queryset.filter(published=True).update(published=False)
    messages.info(request, f"Unpublished {count} objects")


@admin.action(permissions=["reopen"], description="Reopen selected assets")
def reopen_asset_action(modeladmin, request, queryset):
    # Can only reopen completed assets
    assets = queryset.filter(transcription_status=TranscriptionStatus.COMPLETED)

    # Count the number of assets that will become reopened
    count = assets.count()

    """
    For each asset, create a new transcription that:
    - supersedes the currently-latest transcription
    - has rejected set to now
    - has reviewed_by set to the current user
    - has the same transcription text as the latest transcription
    Don't use bulk_create because then the post-save signal will not be sent.

    """
    for asset in assets:
        latest_transcription = asset.transcription_set.order_by("-pk").first()
        new_transcription = Transcription(
            supersedes=latest_transcription,
            rejected=now(),
            reviewed_by=request.user,
            text=latest_transcription.text,
            asset=asset,
            user=request.user,
        )
        new_transcription.full_clean()
        new_transcription.save()

    messages.info(request, f"Reopened {count} assets")


@admin.action(permissions=["reopen"], description="Change status to Completed")
def change_status_to_completed(modeladmin, request, queryset):
    assets = queryset.filter(
        transcription_status=TranscriptionStatus.SUBMITTED
    ).exclude(transcription__user=request.user)
    count = assets.count()
    for asset in assets:
        latest_transcription = asset.transcription_set.order_by("-pk").first()
        latest_transcription.accepted = now()
        latest_transcription.reviewed_by = request.user
        latest_transcription.full_clean()
        latest_transcription.save()

    messages.info(request, f"Changed status of {count} assets to complete")


@admin.action(permissions=["reopen"], description="Change status to Needs Review")
def change_status_to_needs_review(modeladmin, request, queryset):
    # Completed -> Needs Review (Submitted)
    assets = queryset.filter(transcription_status=TranscriptionStatus.COMPLETED)
    count = assets.count()
    for asset in assets:
        latest_transcription = asset.transcription_set.order_by("-pk").first()
        new_transcription = Transcription(
            supersedes=latest_transcription,
            submitted=now(),
            reviewed_by=request.user,
            text=latest_transcription.text,
            asset=asset,
            user=request.user,
        )
    new_transcription.full_clean()
    new_transcription.save()

    messages.info(request, f"Changed status of {count} assets to Needs Review")
