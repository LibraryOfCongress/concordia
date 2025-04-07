from django.db import transaction
from django.db.models import Case, IntegerField, Subquery, When

from concordia import models as concordia_models
from concordia.utils.celery import get_registered_task


def find_new_reviewable_topic_assets(topic, user=None):
    # Filtering this to the topic would be more costly than just getting all ids
    # in most cases because it requires joining the asset table to the item table to
    # the project table to the topic table.
    reserved_asset_ids = concordia_models.AssetTranscriptionReservation.objects.values(
        "asset_id"
    )
    next_asset_ids = concordia_models.NextReviewableTopicAsset.objects.filter(
        topic=topic
    ).values("asset_id")

    queryset = (
        concordia_models.Asset.objects.filter(
            item__project__topics=topic.id,
            item__project__published=True,
            item__published=True,
            published=True,
        )
        .filter(transcription_status=concordia_models.TranscriptionStatus.SUBMITTED)
        .exclude(pk__in=Subquery(reserved_asset_ids))
        .exclude(pk__in=Subquery(next_asset_ids))
        .order_by("sequence")
    )
    if user:
        queryset = queryset.exclude(transcription__user=user.id)
    return queryset


def find_next_reviewable_topic_assets(topic, user):
    return concordia_models.NextReviewableTopicAsset.objects.filter(
        topic=topic
    ).exclude(transcriber_ids__contains=[user.id])


@transaction.atomic
def find_reviewable_topic_asset(topic, user):
    next_asset = (
        find_next_reviewable_topic_assets(topic, user)
        .select_for_update(skip_locked=True, of=("self",))
        .values_list("asset_id", flat=True)
        .first()
    )
    if next_asset:
        asset_query = concordia_models.Asset.objects.filter(id=next_asset)
    else:
        # No asset in the NextReviewableTopicAsset table for this topic,
        # so fallback to manually finding on
        asset_query = find_new_reviewable_topic_assets(topic, user)
        # Spawn a task to populate the table for this topic
        populate_task = get_registered_task(
            "concordia.tasks.populate_next_reviewable_for_topic"
        )
        populate_task.delay(topic.id)
    # select_for_update(of=("self",)) causes the row locking only to
    # apply to the Asset table, rather than also locking joined item table
    return (
        asset_query.select_for_update(skip_locked=True, of=("self",))
        .select_related("item", "item__project")
        .first()
    )


def find_and_order_potential_reviewable_topic_assets(
    topic, user, project_slug, item_id, asset_pk
):
    potential_next_assets = find_next_reviewable_topic_assets(topic, user)

    # We'll favor assets which are in the same item or project as the original:
    potential_next_assets = potential_next_assets.annotate(
        same_project=Case(
            When(project_slug=project_slug, then=1),
            default=0,
            output_field=IntegerField(),
        ),
        same_item=Case(
            When(item_item_id=item_id, then=1), default=0, output_field=IntegerField()
        ),
        next_asset=Case(
            When(asset_id__gt=asset_pk, then=1), default=0, output_field=IntegerField()
        ),
    ).order_by("-next_asset", "-same_project", "-same_item", "sequence")

    return potential_next_assets


def find_next_reviewable_topic_asset(
    topic, user, project_slug, item_id, original_asset_id
):
    potential_next_assets = find_and_order_potential_reviewable_topic_assets(
        topic, user, project_slug, item_id, original_asset_id
    )
    asset_id = (
        potential_next_assets.select_for_update(skip_locked=True, of=("self",))
        .values_list("asset_id", flat=True)
        .first()
    )
    if asset_id:
        asset_query = concordia_models.Asset.objects.filter(id=asset_id)
    else:
        # Since we had no potential next assets in the caching table, we have to check
        # the asset table directly.
        asset_query = find_new_reviewable_topic_assets(topic, user)
        asset_query = asset_query.annotate(
            same_project=Case(
                When(item__project__slug=project_slug, then=1),
                default=0,
                output_field=IntegerField(),
            ),
            same_item=Case(
                When(item__item_id=item_id, then=1),
                default=0,
                output_field=IntegerField(),
            ),
            next_asset=Case(
                When(id__gt=original_asset_id, then=1),
                default=0,
                output_field=IntegerField(),
            ),
        ).order_by("-next_asset", "-same_project", "-same_item", "sequence")
        # Spawn a task to populate the table for this topic
        populate_task = get_registered_task(
            "concordia.tasks.populate_next_reviewable_for_topic"
        )
        populate_task.delay(topic.id)

    return (
        asset_query.select_for_update(skip_locked=True, of=("self",))
        .select_related("item", "item__project")
        .first()
    )
