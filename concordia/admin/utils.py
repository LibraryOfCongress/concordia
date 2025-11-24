from django.contrib.auth.models import User
from django.db.models import QuerySet
from django.utils.timezone import now

from ..models import Asset, Transcription


def _change_status(
    user: User,
    assets: QuerySet[Asset],
    submit: bool = True,
) -> int:
    """
    Create review transcriptions to move assets to a new workflow status.

    For each asset in `assets` this helper creates a new `Transcription` that
    supersedes the latest transcription when one exists. The new transcription
    copies the latest text and records the current user as the reviewer. It
    sets `submitted` when `submit` is true, otherwise it sets `rejected`.
    Signals are preserved because this does not use `bulk_create`.

    Args:
        user (User): user to assign as reviewer.
        assets (QuerySet[Asset]): Assets whose status should be updated.
        submit (bool): When true mark transcriptions as submitted, otherwise
            mark them as rejected.

    Returns:
        int: Number of assets that were processed.
    """
    # Count the number of assets that will be updated
    count = assets.count()
    for asset in assets:
        latest_transcription = asset.transcription_set.order_by("-pk").first()
        kwargs = {
            "reviewed_by": user,
            "asset": asset,
            "user": user,
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
