from django.db import transaction
from django.db.models import Case, IntegerField, Q, Subquery, When

from concordia import models as concordia_models
from concordia.utils.celery import get_registered_task


def find_new_transcribable_topic_assets(topic):
    """
    Returns a queryset of assets in the given topic that are eligible for transcription
    caching.

    This excludes:
    - Assets with transcription_status not NOT_STARTED or IN_PROGRESS
    - Assets currently reserved
    - Assets already present in the NextTranscribableTopicAsset table

    Args:
        topic (Topic): The topic to filter assets by.

    Returns:
        QuerySet: Eligible assets ordered by sequence.
    """

    # Filtering this to the topic would be more costly than just getting all ids
    # in most cases because it requires joining the asset table to the item table to
    # the project table to the topic table.
    reserved_asset_ids = concordia_models.AssetTranscriptionReservation.objects.values(
        "asset_id"
    )
    next_asset_ids = concordia_models.NextTranscribableTopicAsset.objects.filter(
        topic=topic
    ).values("asset_id")

    return (
        concordia_models.Asset.objects.filter(
            item__project__topics=topic.id,
            item__project__published=True,
            item__published=True,
            published=True,
        )
        .filter(
            Q(transcription_status=concordia_models.TranscriptionStatus.NOT_STARTED)
            | Q(transcription_status=concordia_models.TranscriptionStatus.IN_PROGRESS)
        )
        .exclude(pk__in=Subquery(reserved_asset_ids))
        .exclude(pk__in=Subquery(next_asset_ids))
        .order_by("sequence")
    )


def find_next_transcribable_topic_assets(topic):
    """
    Returns all cached transcribable assets for a topic.

    This accesses the NextTranscribableTopicAsset cache table for the given topic.

    Args:
        topic (Topic): The topic to retrieve cached assets for.

    Returns:
        QuerySet: Cached assets
    """

    return concordia_models.NextTranscribableTopicAsset.objects.filter(topic=topic)


@transaction.atomic
def find_transcribable_topic_asset(topic):
    """
    Retrieves a single transcribable asset from the topic.

    Attempts to retrieve an asset from the cache table (NextTranscribableTopicAsset).
    If no eligible asset is found, falls back to computing one directly from the
    Asset table and asynchronously schedules a background task to repopulate the cache.

    Ensures database row-level locking to prevent multiple concurrent consumers
    from selecting the same asset.

    Args:
        topic (Topic): The topic to retrieve an asset from.

    Returns:
        Asset or None: A locked asset eligible for transcription, or None if
        unavailable.
    """

    next_asset = (
        find_next_transcribable_topic_assets(topic)
        .select_for_update(skip_locked=True, of=("self",))
        .values_list("asset_id", flat=True)
        .first()
    )

    spawn_task = False
    if next_asset:
        asset_query = concordia_models.Asset.objects.filter(id=next_asset)
    else:
        # No asset in the NextTranscribableTopicAsset table for this topic,
        # so fallback to manually finding on
        asset_query = find_new_transcribable_topic_assets(topic)
        spawn_task = True
    # select_for_update(of=("self",)) causes the row locking only to
    # apply to the Asset table, rather than also locking joined item table
    asset = (
        asset_query.select_for_update(skip_locked=True, of=("self",))
        .select_related("item", "item__project")
        .first()
    )
    if spawn_task:
        # Spawn a task to populate the table for this topic
        # We wait to do this until after getting an asset because otherwise there's a
        # a chance all valid assets get grabbed by the task and our query will return
        # nothing
        populate_task = get_registered_task(
            "concordia.tasks.populate_next_transcribable_for_topic"
        )
        populate_task.delay(topic.id)
    return asset


def find_and_order_potential_transcribable_topic_assets(
    topic, project_slug, item_id, asset_pk
):
    """
    Retrieves and prioritizes cached transcribable assets based on proximity and status.

    Orders results from NextTranscribableTopicAsset by:
    - Whether the asset comes after the given asset in sequence
    - Whether the asset is in the NOT_STARTED state
    - Whether the asset belongs to the same project
    - Whether the asset belongs to the same item

    Args:
        topic (Topic): The topic to filter assets by.
        project_slug (str): Slug of the original asset's project.
        item_id (str): Item ID of the original asset.
        asset_pk (int): Primary key of the original asset.

    Returns:
        QuerySet: Prioritized list of candidate assets.
    """

    potential_next_assets = find_next_transcribable_topic_assets(topic)

    # We'll favor assets which are in the same item or project as the original:
    potential_next_assets = potential_next_assets.annotate(
        unstarted=Case(
            When(
                transcription_status=concordia_models.TranscriptionStatus.NOT_STARTED,
                then=1,
            ),
            default=0,
            output_field=IntegerField(),
        ),
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
    ).order_by("-next_asset", "-unstarted", "-same_project", "-same_item", "sequence")

    return potential_next_assets


@transaction.atomic
def find_next_transcribable_topic_asset(
    topic, project_slug, item_id, original_asset_id
):
    """
    Retrieves the next best transcribable asset for a user within a topic.

    Prioritizes assets from the cache that are:
    - After the current asset in sequence
    - In the NOT_STARTED state
    - In the same project or item

    Falls back to computing candidates if the cache is empty, and triggers
    a background task to repopulate the cache after selection.

    Args:
        topic (Topic): The topic to find an asset in.
        project_slug (str): Slug of the project the user is currently transcribing.
        item_id (str): ID of the item the user is currently transcribing.
        original_asset_id (int): ID of the asset the user just transcribed.

    Returns:
        Asset or None: A locked asset eligible for transcription, or None if
        unavailable.
    """

    potential_next_assets = find_and_order_potential_transcribable_topic_assets(
        topic, project_slug, item_id, original_asset_id
    )
    asset_id = (
        potential_next_assets.select_for_update(skip_locked=True, of=("self",))
        .values_list("asset_id", flat=True)
        .first()
    )

    spawn_task = False
    if asset_id:
        asset_query = concordia_models.Asset.objects.filter(id=asset_id)
    else:
        spawn_task = True
        # Since we had no potential next assets in the caching table, we have to check
        # the asset table directly.
        asset_query = find_new_transcribable_topic_assets(topic)
        asset_query = asset_query.annotate(
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
                When(item__item_id=item_id, then=1),
                default=0,
                output_field=IntegerField(),
            ),
            next_asset=Case(
                When(id__gt=original_asset_id, then=1),
                default=0,
                output_field=IntegerField(),
            ),
        ).order_by(
            "-next_asset", "-unstarted", "-same_project", "-same_item", "sequence"
        )

    asset = (
        asset_query.select_for_update(skip_locked=True, of=("self",))
        .select_related("item", "item__project")
        .first()
    )
    if spawn_task:
        # Spawn a task to populate the table for this topic
        # We wait to do this until after getting an asset because otherwise there's a
        # a chance all valid assets get grabbed by the task and our query will return
        # nothing
        populate_task = get_registered_task(
            "concordia.tasks.populate_next_transcribable_for_topic"
        )
        populate_task.delay(topic.id)

    return asset


def find_invalid_next_transcribable_topic_assets(topic_id):
    """
    Returns a queryset of NextTranscribableTopicAsset records that are no longer valid
    for transcription. This includes:
    - Assets with a transcription status other than NOT_STARTED or IN_PROGRESS.
    - Assets currently reserved via AssetTranscriptionReservation.

    Args:
        topic_id (int): The ID of the topic to filter by.

    Returns:
        QuerySet: Invalid NextTranscribableTopicAsset records.
    """
    reserved_asset_ids = concordia_models.AssetTranscriptionReservation.objects.filter(
        asset__item__project__topics=topic_id
    ).values("asset_id")

    status_filtered = concordia_models.NextTranscribableTopicAsset.objects.filter(
        topic_id=topic_id
    ).exclude(
        asset__transcription_status__in=[
            concordia_models.TranscriptionStatus.NOT_STARTED,
            concordia_models.TranscriptionStatus.IN_PROGRESS,
        ]
    )

    reserved_filtered = concordia_models.NextTranscribableTopicAsset.objects.filter(
        topic_id=topic_id, asset_id__in=Subquery(reserved_asset_ids)
    )

    return (status_filtered | reserved_filtered).distinct()
