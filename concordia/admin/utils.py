from django.utils.timezone import now

from ..models import Transcription


def _change_status(user, assets, submit=True):
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
        if hasattr(asset, "prefetched_transcriptions"):
            latest_transcription = asset.prefetched_transcriptions[0]
        else:
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
