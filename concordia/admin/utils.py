from django.contrib.auth.models import User
from django.db.models import QuerySet
from django.utils.timezone import now

from ..models import Asset, Transcription, TranscriptionStatus


def _change_status(
    user: User,
    assets: QuerySet[Asset],
    status: str = TranscriptionStatus.SUBMITTED,
) -> int:
    """
    Create transcriptions to move assets to a new workflow status.

    For each asset in `assets` this helper creates a new `Transcription` that
    supersedes the latest transcription when one exists. The new transcription
    copies the latest text. Reviewer is only assigned for accepted/rejected.
    It sets the appropriate timestamp depending on `status`. Signals are
    preserved because this does not use `bulk_create`.

    Args:
        user (User): user performing the action.
        assets (QuerySet[Asset]): Assets whose status should be updated.
        status (str): Workflow status to apply. Supported values are constants
        from TranscriptionStatus: NOT_STARTED, IN_PROGRESS, SUBMITTED, COMPLETED.

    Returns:
        int: Number of assets that were processed.
    """
    # Count the number of assets that will be updated
    count = assets.count()
    for asset in assets:
        latest_transcription = asset.transcription_set.order_by("-pk").first()
        kwargs = {
            "asset": asset,
        }
        if latest_transcription is not None:
            kwargs.update(
                **{
                    "supersedes": latest_transcription,
                    "text": latest_transcription.text,
                }
            )
        if status == TranscriptionStatus.SUBMITTED:
            kwargs["user"] = user
            kwargs["submitted"] = now()
        elif status == TranscriptionStatus.COMPLETED:
            kwargs["user"] = latest_transcription.user
            kwargs["accepted"] = now()
            kwargs["reviewed_by"] = user
        elif status == TranscriptionStatus.IN_PROGRESS:
            if (
                latest_transcription
                and latest_transcription.accepted
                and not latest_transcription.rejected
            ):
                kwargs["user"] = latest_transcription.user
                kwargs["rejected"] = now()
                kwargs["reviewed_by"] = user
        elif status != TranscriptionStatus.NOT_STARTED:
            raise ValueError(f"Unsupported status: {status}")
        new_transcription = Transcription(**kwargs)
        new_transcription.full_clean()
        new_transcription.save()

    return count
