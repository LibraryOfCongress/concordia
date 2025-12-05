import uuid
from logging import getLogger

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest
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
from .utils import _change_status

logger = getLogger(__name__)


@admin.action(
    permissions=["change"],
    description="Anonymize and disable user accounts",
)
def anonymize_action(
    modeladmin: admin.ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet,
) -> None:
    """
    Anonymize and disable selected user accounts.

    Replaces identifying fields of each user account with placeholder values,
    sets the account to inactive, and removes staff and superuser status.
    Records a message with the number of accounts changed.

    Args:
        modeladmin (admin.ModelAdmin): Admin class that owns this action.
        request (HttpRequest): Current request.
        queryset (QuerySet): Selected user accounts to anonymize.

    Returns:
        None
    """
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
        request,
        f"Anonymized and disabled {count} user accounts",
        fail_silently=True,
    )


@admin.action(permissions=["change"], description="Publish selected items and assets")
def publish_item_action(
    modeladmin: admin.ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet[Item],
) -> None:
    """
    Publish selected items and their related assets.

    Marks each selected `Item` as published and updates any related `Asset`
    instances that are not yet published. Records a message with the number
    of items and assets changed.

    Args:
        modeladmin (admin.ModelAdmin): Admin class that owns this action.
        request (HttpRequest): Current request.
        queryset (QuerySet[Item]): Selected items to publish.

    Returns:
        None
    """
    count = queryset.filter(published=False).update(published=True)
    asset_count = Asset.objects.filter(item__in=queryset, published=False).update(
        published=True
    )

    messages.info(
        request,
        f"Published {count} items and {asset_count} assets",
        fail_silently=True,
    )


@admin.action(
    permissions=["change"],
    description="Unpublish selected items and assets",
)
def unpublish_item_action(
    modeladmin: admin.ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet[Item],
) -> None:
    """
    Unpublish selected items and their related assets.

    Marks each selected `Item` as unpublished and updates any related `Asset`
    instances that are currently published. Records a message with the number
    of items and assets changed.

    Args:
        modeladmin (admin.ModelAdmin): Admin class that owns this action.
        request (HttpRequest): Current request.
        queryset (QuerySet[Item]): Selected items to unpublish.

    Returns:
        None
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
def publish_action(
    modeladmin: admin.ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet,
) -> None:
    """
    Publish selected objects.

    Marks each selected object in the queryset as published. This action
    assumes the target model has a boolean `published` field. Records a
    message with the number of objects changed.

    Args:
        modeladmin (admin.ModelAdmin): Admin class that owns this action.
        request (HttpRequest): Current request.
        queryset (QuerySet): Selected objects to publish.

    Returns:
        None
    """
    count = queryset.filter(published=False).update(published=True)
    messages.info(request, f"Published {count} objects", fail_silently=True)


@admin.action(permissions=["change"], description="Unpublish selected")
def unpublish_action(
    modeladmin: admin.ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet,
) -> None:
    """
    Unpublish selected objects.

    Marks each selected object in the queryset as unpublished. This action
    assumes the target model has a boolean `published` field. Records a
    message with the number of objects changed.

    Args:
        modeladmin (admin.ModelAdmin): Admin class that owns this action.
        request (HttpRequest): Current request.
        queryset (QuerySet): Selected objects to unpublish.

    Returns:
        None
    """
    count = queryset.filter(published=True).update(published=False)
    messages.info(request, f"Unpublished {count} objects", fail_silently=True)


@admin.action(permissions=["reopen"], description="Change status to Completed")
def change_status_to_completed(
    modeladmin: admin.ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet[Asset],
) -> None:
    """
    Mark selected assets as completed by accepting a transcription.

    For each asset whose `transcription_status` is not
    `TranscriptionStatus.COMPLETED`, accepts the latest transcription or
    creates a new one if none exists. The new or updated transcription is
    marked as accepted by the current user and validated before saving.
    Records a message describing which assets were changed.

    Args:
        modeladmin (admin.ModelAdmin): Admin class that owns this action.
        request (HttpRequest): Current request.
        queryset (QuerySet[Asset]): Selected assets to mark as completed.

    Returns:
        None
    """
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
            request,
            f"Changed status of {count} assets to Complete",
            fail_silently=True,
        )


@admin.action(permissions=["reopen"], description="Change status to Needs Review")
def change_status_to_needs_review(
    modeladmin: admin.ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet[Asset],
) -> None:
    """
    Move selected assets to the Needs Review workflow status.

    Filters out assets that are already submitted, then calls `_change_status`
    to create new submitted transcriptions reviewed by the current user.
    Records a message describing which assets were changed.

    Args:
        modeladmin (admin.ModelAdmin): Admin class that owns this action.
        request (HttpRequest): Current request.
        queryset (QuerySet[Asset]): Selected assets to move to Needs Review.

    Returns:
        None
    """
    eligible = queryset.exclude(transcription_status=TranscriptionStatus.SUBMITTED)
    count = _change_status(request.user, eligible, status="submitted")

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
def change_status_to_in_progress(
    modeladmin: admin.ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet[Asset],
) -> None:
    """
    Move selected assets to the In Progress workflow status.

    Filters out assets that are already in progress, then calls
    `_change_status` with `submit` set to false to create new rejected
    transcriptions reviewed by the current user. Records a message describing
    which assets were changed.

    Args:
        modeladmin (admin.ModelAdmin): Admin class that owns this action.
        request (HttpRequest): Current request.
        queryset (QuerySet[Asset]): Selected assets to move to In Progress.

    Returns:
        None
    """
    eligible = queryset.exclude(transcription_status=TranscriptionStatus.IN_PROGRESS)
    count = _change_status(request.user, eligible, status="in_progress")

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
def verify_assets_action(
    modeladmin: admin.ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet,
) -> None:
    """
    Create image verification jobs for assets related to the selected objects.

    Depending on which admin model invoked this action, it collects asset
    primary keys from the selected `Campaign`, `Project`, `Item` or `Asset`
    instances. It then calls `create_verify_asset_image_job_batch` to create
    a batch of verification jobs and shows a link to the batch in the admin
    messages.

    Args:
        modeladmin (admin.ModelAdmin): Admin class that owns this action.
        request (HttpRequest): Current request.
        queryset (QuerySet): Selected objects used to look up assets.

    Returns:
        None
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
        asset_pks = Asset.objects.filter(item__in=queryset).values_list(
            "id",
            flat=True,
        )
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
