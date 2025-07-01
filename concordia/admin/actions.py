import uuid
from logging import getLogger

from django.contrib import admin, messages
from django.utils.timezone import now

from importer.utils import create_verify_asset_image_job_batch

from ..models import (
    Asset,
    Campaign,
    Item,
    Project,
    Transcription,
    TranscriptionStatus,
)

logger = getLogger(__name__)


@admin.action(permissions=["change"], description="Anonymize and disable user accounts")
def anonymize_action(modeladmin, request, queryset):
    count = queryset.count()
    for user_account in queryset:
        user_account.username = "Anonymized %s" % uuid.uuid4()
        user_account.first_name = ""
        user_account.last_name = ""
        user_account.email = ""
        user_account.set_unusable_password()
        user_account.is_staff = False
        user_account.is_superuser = False
        user_account.is_active = False
        user_account.save()

    messages.info(
        request, f"Anonymized and disabled {count} user accounts", fail_silently=True
    )


@admin.action(permissions=["change"], description="Publish selected items and assets")
def publish_item_action(modeladmin, request, queryset):
    """
    Mark all of the selected items and their related assets as published
    """

    count = queryset.filter(published=False).update(published=True)
    asset_count = Asset.objects.filter(item__in=queryset, published=False).update(
        published=True
    )

    messages.info(
        request, f"Published {count} items and {asset_count} assets", fail_silently=True
    )


@admin.action(permissions=["change"], description="Unpublish selected items and assets")
def unpublish_item_action(modeladmin, request, queryset):
    """
    Mark all of the selected items and their related assets as unpublished
    """

    count = queryset.filter(published=True).update(published=False)
    asset_count = Asset.objects.filter(item__in=queryset, published=True).update(
        published=False
    )

    messages.info(
        request,
        f"Unpublished {count} items and {asset_count} assets",
        fail_silently=True,
    )


@admin.action(permissions=["change"], description="Publish selected")
def publish_action(modeladmin, request, queryset):
    """
    Mark all of the selected objects as published
    """

    count = queryset.filter(published=False).update(published=True)
    messages.info(request, f"Published {count} objects", fail_silently=True)


@admin.action(permissions=["change"], description="Unpublish selected")
def unpublish_action(modeladmin, request, queryset):
    """
    Mark all of the selected objects as unpublished
    """

    count = queryset.filter(published=True).update(published=False)
    messages.info(request, f"Unpublished {count} objects", fail_silently=True)


@admin.action(permissions=["reopen"], description="Change status to Completed")
def change_status_to_completed(modeladmin, request, queryset):
    assets = queryset.exclude(transcription_status=TranscriptionStatus.COMPLETED)
    count = assets.count()
    if count == 1:
        changed_asset = assets.first()
    else:
        changed_asset = False

    for asset in assets:
        latest_transcription = asset.transcription_set.order_by("-pk").first()
        if latest_transcription is None:
            kwargs = {
                "asset": asset,
                "user": request.user,
            }
            latest_transcription = Transcription(**kwargs)
        latest_transcription.accepted = now()
        latest_transcription.rejected = None
        latest_transcription.reviewed_by = request.user
        latest_transcription.clean_fields()
        latest_transcription.validate_unique()
        latest_transcription.save()

    if changed_asset:
        messages.info(
            request,
            f"Changed status of {changed_asset.title} to Complete",
            fail_silently=True,
        )
    else:
        messages.info(
            request, f"Changed status of {count} assets to Complete", fail_silently=True
        )


def _change_status(request, assets, submit=True):
    # Count the number of assets that will be updated
    count = assets.count()
    """
    For each asset:
    - create a new transcription. if transcriptions already exist:
      - supersede the currently-latest transcription
      - use the same transcription text as the latest transcription
    - set either submitted or rejected to now
    - set reviewed_by to the current user
    Don't use bulk_create, because then the post-save signal will not be sent.

    """
    for asset in assets:
        latest_transcription = asset.transcription_set.order_by("-pk").first()
        kwargs = {
            "reviewed_by": request.user,
            "asset": asset,
            "user": request.user,
        }
        if latest_transcription is not None:
            kwargs.update(
                **{
                    "supersedes": latest_transcription,
                    "text": latest_transcription.text,
                }
            )
        if submit:
            kwargs["submitted"] = now()
        else:
            kwargs["rejected"] = now()
        new_transcription = Transcription(**kwargs)
        new_transcription.full_clean()
        new_transcription.save()

    return count


@admin.action(permissions=["reopen"], description="Change status to Needs Review")
def change_status_to_needs_review(modeladmin, request, queryset):
    eligible = queryset.exclude(transcription_status=TranscriptionStatus.SUBMITTED)
    count = _change_status(request, eligible)

    if count == 1:
        asset = queryset.first()
        messages.info(
            request,
            f"Changed status of {asset.title} to Needs Review",
            fail_silently=True,
        )
    else:
        messages.info(
            request,
            f"Changed status of {count} assets to Needs Review",
            fail_silently=True,
        )


@admin.action(permissions=["reopen"], description="Change status to In Progress")
def change_status_to_in_progress(modeladmin, request, queryset):
    eligible = queryset.exclude(transcription_status=TranscriptionStatus.IN_PROGRESS)
    count = _change_status(request, eligible, submit=False)

    if count == 1:
        asset = queryset.first()
        messages.info(
            request,
            f"Changed status of {asset.title} to In Progress",
            fail_silently=True,
        )
    else:
        messages.info(
            request,
            f"Changed status of {count} assets to In Progress",
            fail_silently=True,
        )


@admin.action(
    permissions=["change"],
    description="Verify images for all assets for selected objects",
)
def verify_assets_action(modeladmin, request, queryset):
    """
    Django admin action that verifies assets under the selected
    Campaigns, Projects, Items or Assets.
    """
    batch = str(uuid.uuid4())

    if modeladmin.model == Campaign:
        asset_pks = Asset.objects.filter(campaign__in=queryset).values_list(
            "id", flat=True
        )
    elif modeladmin.model == Project:
        asset_pks = Asset.objects.filter(item__project__in=queryset).values_list(
            "id", flat=True
        )
    elif modeladmin.model == Item:
        asset_pks = Asset.objects.filter(item__in=queryset).values_list("id", flat=True)
    elif modeladmin.model == Asset:
        asset_pks = queryset.values_list("id", flat=True)
    else:
        modeladmin.message_user(
            request, "This action is not available for this model.", level="error"
        )
        return

    job_count, url = create_verify_asset_image_job_batch(asset_pks, batch)

    modeladmin.message_user(
        request,
        f"Created {job_count} VerifyAssetImageJobs as part of batch {batch}. "
        f'<a href="{url}" target="_blank">View the created jobs</a>',
        extra_tags="marked-safe",
    )
