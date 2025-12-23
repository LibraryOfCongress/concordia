from django.contrib.auth.models import User
from django.db.models import Prefetch
from django.utils.timezone import now

from ..models import Asset, Transcription, TranscriptionStatus
from ..utils import get_anonymous_user


def _change_status(
    request_user: User,
    asset: Asset,
    status: str = TranscriptionStatus.SUBMITTED,
    transcription_user: User = None,
) -> int:
    """
    Create transcriptions to move assets to a new workflow status.

    For each asset in `assets` this helper creates a new `Transcription` that
    supersedes the latest transcription when one exists. The new transcription
    copies the latest text. Reviewer is only assigned for accepted/rejected.
    It sets the appropriate timestamp depending on `status`. Signals are
    preserved because this does not use `bulk_create`.

    Args:
        reviewer (User): user performing the action.
        assets (QuerySet[Asset]): Assets whose status should be updated.
        status (str): Workflow status to apply. Supported values are constants
        user (User): User that should be credited with submitting the
                    transcription. Defaults to None
        from TranscriptionStatus: NOT_STARTED, IN_PROGRESS, SUBMITTED, COMPLETED.
    Returns:
        int: 1 if asset was updated, otherwise 0
    """
    latest_transcription = (
        asset.prefetched_transcriptions[0] if asset.prefetched_transcriptions else None
    )

    if status == TranscriptionStatus.NOT_STARTED:
        return 0

    kwargs = {
        "asset": asset,
        "user": transcription_user or get_anonymous_user(),
    }
    if latest_transcription is not None:
        kwargs.update(
            **{
                "supersedes": latest_transcription,
                "text": latest_transcription.text,
            }
        )

    if status == TranscriptionStatus.SUBMITTED:
        kwargs["submitted"] = now()
    elif status == TranscriptionStatus.COMPLETED:
        kwargs["reviewed_by"] = request_user
        kwargs["accepted"] = now()
    elif status == TranscriptionStatus.IN_PROGRESS:
        if (
            latest_transcription
            and latest_transcription.status == TranscriptionStatus.COMPLETED
        ):
            kwargs["rejected"] = now()
        kwargs["reviewed_by"] = request_user

    transcription = Transcription(**kwargs)
    transcription.full_clean()
    transcription.save()
    return 1


def _bulk_change_status(
    request_user: User,
    rows: list,
) -> int:
    """
    Bulk update assets by delegating to _change_status
    Args:
        request_user: the staff user performing the bulk change.
        asset_rows: iterable of dicts like:
            {"asset": Asset, "status": TranscriptionStatus.SUBMITTED, "user": User}
    """
    slugs = [row["slug"] for row in rows if row.get("slug")]
    assets = Asset.objects.filter(slug__in=slugs).prefetch_related(
        Prefetch(
            "transcription_set",
            queryset=Transcription.objects.order_by("-pk"),
            to_attr="prefetched_transcriptions",
        )
    )
    asset_map = {asset.slug: asset for asset in assets}

    updated_total = 0
    for row in rows:
        asset = asset_map.get(row.get("slug"))
        if asset:
            updated_total += _change_status(
                request_user, asset, row["status"], row.get("user")
            )

    return updated_total
