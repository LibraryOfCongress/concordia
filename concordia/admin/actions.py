from django.contrib import messages
from django.utils.timezone import now

from ..models import Asset, Transcription, TranscriptionStatus


def publish_item_action(modeladmin, request, queryset):
    """
    Mark all of the selected items and their related assets as published
    """

    count = queryset.filter(published=False).update(published=True)
    asset_count = Asset.objects.filter(item__in=queryset, published=False).update(
        published=True
    )

    messages.info(request, f"Published {count} items and {asset_count} assets")


publish_item_action.short_description = "Publish selected items and assets"


def unpublish_item_action(modeladmin, request, queryset):
    """
    Mark all of the selected items and their related assets as unpublished
    """

    count = queryset.filter(published=True).update(published=False)
    asset_count = Asset.objects.filter(item__in=queryset, published=True).update(
        published=False
    )

    messages.info(request, f"Unpublished {count} items and {asset_count} assets")


unpublish_item_action.short_description = "Unpublish selected items and assets"


def publish_action(modeladmin, request, queryset):
    """
    Mark all of the selected objects as published
    """

    count = queryset.filter(published=False).update(published=True)
    messages.info(request, f"Published {count} objects")


publish_action.short_description = "Publish selected"


def unpublish_action(modeladmin, request, queryset):
    """
    Mark all of the selected objects as unpublished
    """

    count = queryset.filter(published=True).update(published=False)
    messages.info(request, f"Unpublished {count} objects")


unpublish_action.short_description = "Unpublish selected"


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


reopen_asset_action.short_description = "Reopen selected assets"
