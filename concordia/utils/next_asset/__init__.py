from django.db.models import Case, IntegerField, Q, Subquery, When

from concordia import models as concordia_models

from .campaign import (
    find_and_order_potential_transcribable_campaign_assets,
    find_new_transcribable_campaign_assets,
    find_next_transcribable_campaign_asset,
    find_next_transcribable_campaign_assets,
    find_transcribable_campaign_asset,
)

__all__ = [
    "filter_and_order_transcribable_assets",
    "find_new_transcribable_campaign_assets",
    "find_next_transcribable_campaign_assets",
    "find_transcribable_campaign_asset",
    "find_and_order_potential_transcribable_campaign_assets",
    "find_next_transcribable_campaign_asset",
]


def filter_and_order_transcribable_assets(
    potential_assets, project_slug, item_id, asset_id
):
    potential_assets = potential_assets.filter(
        Q(transcription_status=concordia_models.TranscriptionStatus.NOT_STARTED)
        | Q(transcription_status=concordia_models.TranscriptionStatus.IN_PROGRESS)
    )

    potential_assets = potential_assets.exclude(
        pk__in=Subquery(
            concordia_models.AssetTranscriptionReservation.objects.values("asset_id")
        )
    )
    potential_assets = potential_assets.select_related("item", "item__project")

    # We'll favor assets which are in the same item or project as the original:
    potential_assets = potential_assets.annotate(
        unstarted=Case(
            When(
                transcription_status=concordia_models.TranscriptionStatus.NOT_STARTED,
                then=1,
            ),
            default=0,
            output_field=IntegerField(),
        ),
        same_project=Case(
            When(item__project__slug=project_slug, then=1),
            default=0,
            output_field=IntegerField(),
        ),
        same_item=Case(
            When(item__item_id=item_id, then=1), default=0, output_field=IntegerField()
        ),
        next_asset=Case(
            When(pk__gt=asset_id, then=1), default=0, output_field=IntegerField()
        ),
    ).order_by("-next_asset", "-unstarted", "-same_project", "-same_item", "sequence")

    return potential_assets
