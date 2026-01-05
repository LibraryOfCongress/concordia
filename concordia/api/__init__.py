"""
Experimental API endpoints backing the React transcription page.

Status
------
This module is in active development and not yet in its final form. Interfaces
and behavior may change without deprecation.

Intended Use
------------
These endpoints exist to support the React app's transcription page during
ongoing development and trial rollout.

Duplication and Future Plan
---------------------------
To enable rapid iteration, this module currently duplicates substantial logic
from existing Django views (e.g., validation, submission/review workflows,
rollback/rollforward and serialization). When the React transcription page is
ready for production, one of the following will occur:

1. Shared logic will be factored into reusable helpers imported by both these
   endpoints and the legacy views; or
2. The legacy views that these endpoints duplicate will be removed.

Until then, expect overlap and keep changes synchronized across both places.

Note
----
The React app still requires significant development work. Treat these endpoints
as provisional and subject to change.
"""

import re
from time import time
from typing import Optional

from django.conf import settings
from django.db.transaction import atomic
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.timezone import now
from ninja import NinjaAPI, Router
from ninja.errors import HttpError

from concordia.exceptions import RateLimitExceededError
from concordia.logging import ConcordiaLogger
from concordia.models import (
    Asset,
    CardFamily,
    ConcordiaUser,
    Guide,
    Transcription,
    TranscriptionStatus,
    TutorialCard,
    UserAssetTagCollection,
)
from concordia.templatetags.concordia_media_tags import asset_media_url
from concordia.utils import get_anonymous_user
from concordia.utils.constants import URL_REGEX
from configuration.utils import configuration_value

from .schemas import CamelSchema

structured_logger = ConcordiaLogger.get_logger(__name__)

api = NinjaAPI(version=None, urls_namespace="api")


class AssetOut(CamelSchema):
    """
    Serialized representation of an Asset for API responses.

    Fields mirror what the web client needs to render the asset view,
    including navigation context, image URLs, tagging, tutorial cards,
    available languages and undo/redo availability.
    """

    id: int  # noqa: A003
    title: str
    item_id: str
    project_slug: str
    campaign_slug: str
    transcription: Optional[dict]
    transcription_status: str
    activity_mode: str
    disable_ocr: bool
    previous_asset_url: Optional[str]
    next_asset_url: Optional[str]
    asset_navigation: list[tuple[int, str]]
    image_url: str
    thumbnail_url: str
    current_asset_url: str
    tags: list[str]
    registered_contributors: int
    cards: list[str]
    guides: Optional[list[dict[str, str]]]
    languages: list[tuple[str, str]]
    undo_available: bool
    redo_available: bool


class ReviewIn(CamelSchema):
    """
    Request Parameters:
        action (str): Review action, either `"accept"` or `"reject"`.
    """

    action: str  # "accept" or "reject"


class TranscriptionIn(CamelSchema):
    """
    Request Parameters:
        text (str): The transcription text to save.
        supersedes (Optional[int]): The ID of the transcription being
            superseded.
    """

    text: str
    supersedes: Optional[int]


class OcrTranscriptionIn(CamelSchema):
    """
    Request Parameters:
        language (str): The ISO 639-3 code of the OCR language to use.
        supersedes (Optional[int]): The ID of the transcription being
            superseded.
    """

    language: str
    supersedes: Optional[int]


class TranscriptionOut(CamelSchema):
    """
    Serialized representation of a Transcription event/result returned
    by API endpoints that create or mutate transcriptions.
    """

    id: int  # noqa: A003
    text: str
    sent: float
    submission_url: Optional[str] = None
    asset: AssetOut
    undo_available: bool
    redo_available: bool


def serialize_asset(asset: Asset, request: HttpRequest) -> AssetOut:
    """
    Build the `AssetOut` payload for a single asset.

    Args:
        asset (Asset): Published asset instance to serialize.
        request (HttpRequest): Current request, used for absolute URLs.

    Returns:
        AssetOut: Serialized asset suitable for API responses.
    """
    item = asset.item
    project = item.project
    campaign = project.campaign

    transcription = asset.transcription_set.order_by("-pk").first()
    if transcription:
        transcription_out = {
            "id": transcription.pk,
            "status": transcription.status,
            "text": transcription.text,
            "contributors": asset.get_contributor_count(),
        }
        if transcription.status in TranscriptionStatus.CHOICE_MAP.values():
            transcription_status = [
                k
                for k, v in TranscriptionStatus.CHOICE_MAP.items()
                if v == transcription.status
            ][0]
        else:
            transcription_status = TranscriptionStatus.NOT_STARTED
    else:
        transcription_out = None
        transcription_status = TranscriptionStatus.NOT_STARTED

    if transcription_status in [
        TranscriptionStatus.NOT_STARTED,
        TranscriptionStatus.IN_PROGRESS,
    ]:
        activity_mode = "transcribe"
        disable_ocr = asset.turn_off_ocr()
    elif transcription_status == TranscriptionStatus.SUBMITTED:
        activity_mode = "review"
        disable_ocr = True
    else:
        activity_mode = "transcribe"
        disable_ocr = True

    current_asset_url = request.build_absolute_uri()
    previous_asset = (
        item.asset_set.published()
        .filter(sequence__lt=asset.sequence)
        .order_by("sequence")
        .last()
    )
    next_asset = (
        item.asset_set.published()
        .filter(sequence__gt=asset.sequence)
        .order_by("sequence")
        .first()
    )

    # Build URLs
    previous_asset_url = previous_asset.get_absolute_url() if previous_asset else None
    next_asset_url = next_asset.get_absolute_url() if next_asset else None

    # Navigation list
    asset_navigation = list(
        item.asset_set.published().order_by("sequence").values_list("sequence", "slug")
    )

    # Thumbnail URL
    image_url = asset_media_url(asset)
    if asset.download_url and "iiif" in asset.download_url:
        thumbnail_url = asset.download_url.replace(
            "http://tile.loc.gov", "https://tile.loc.gov"
        ).replace("/pct:100/", "/!512,512/")
    else:
        thumbnail_url = image_url

    # Tags
    tag_groups = UserAssetTagCollection.objects.filter(asset__slug=asset.slug)
    tags = sorted({tag.value for tg in tag_groups for tag in tg.tags.all()})

    # Cards
    if project.campaign.card_family:
        card_family = project.campaign.card_family
    else:
        card_family = CardFamily.objects.filter(default=True).first()
    if card_family:
        cards = list(
            TutorialCard.objects.filter(tutorial=card_family)
            .order_by("order")
            .values_list("card__title", flat=True)
        )
    else:
        cards = []

    # Guides
    guides_qs = Guide.objects.order_by("order").values("title", "body")
    guides = list(guides_qs) if guides_qs.exists() else None

    # Undo/redo availability
    undo_available = asset.can_rollback()[0] if transcription else False
    redo_available = asset.can_rollforward()[0] if transcription else False

    return AssetOut(
        id=asset.id,
        title=asset.title,
        item_id=item.item_id,
        project_slug=project.slug,
        campaign_slug=campaign.slug,
        transcription=transcription_out,
        transcription_status=transcription_status,
        activity_mode=activity_mode,
        disable_ocr=disable_ocr,
        current_asset_url=current_asset_url,
        previous_asset_url=previous_asset_url,
        next_asset_url=next_asset_url,
        asset_navigation=asset_navigation,
        image_url=image_url,
        thumbnail_url=thumbnail_url,
        tags=tags,
        registered_contributors=asset.get_contributor_count(),
        cards=cards,
        guides=guides,
        languages=list(settings.LANGUAGE_CODES.items()),
        undo_available=undo_available,
        redo_available=redo_available,
    )


assets: Router = Router(tags=["assets"])


@assets.get(
    "/{campaign_slug}/{project_slug}/{item_id}/{asset_slug}/",
    response=AssetOut,
    by_alias=True,
)
def asset_detail_by_slugs(
    request: HttpRequest,
    campaign_slug: str,
    project_slug: str,
    item_id: str,
    asset_slug: str,
) -> AssetOut:
    """
    Resolve and return a published asset using slugs and item_id.

    Path Parameters:
        campaign_slug (str): Campaign slug.
        project_slug (str): Project slug.
        item_id (str): Item identifier within the project.
        asset_slug (str): Asset slug.

    Returns:
        AssetOut: Serialized asset record.
    """
    asset = get_object_or_404(
        Asset.objects.published()
        .select_related("item__project__campaign")
        .filter(
            item__project__campaign__slug=campaign_slug,
            item__project__slug=project_slug,
            item__item_id=item_id,
            slug=asset_slug,
        )
    )
    return serialize_asset(asset, request)


@assets.get("/{asset_id}", response=AssetOut, by_alias=True)
def asset_detail(request: HttpRequest, asset_id: int) -> AssetOut:
    """GET /assets/{asset_id}/ - basic asset record."""
    asset = get_object_or_404(
        Asset.objects.published().select_related("item__project__campaign"), pk=asset_id
    )
    return serialize_asset(asset, request)


@assets.post("/{asset_id}/transcriptions", response=TranscriptionOut, by_alias=True)
def create_transcription(
    request: HttpRequest, asset_id: int, payload: TranscriptionIn
) -> TranscriptionOut:
    """
    Create a new draft transcription for the given asset.

    Replaces any open draft transcription and validates content. Mirrors
    the legacy `save_transcription` view.
    """
    asset = get_object_or_404(
        Asset.objects.published().select_related("item__project__campaign"), pk=asset_id
    )

    user = request.user if not request.user.is_anonymous else get_anonymous_user()

    structured_logger.info(
        "API transcription save start",
        event_code="transcription_save_start",
        user=user,
        asset=asset,
    )

    # Validate transcription text (disallow URLs)
    if re.search(URL_REGEX, payload.text):
        structured_logger.warning(
            "API transcription rejected due to URL",
            event_code="transcription_save_rejected",
            reason="URL detected in transcription",
            reason_code="url_detected",
            user=user,
            asset=asset,
        )
        raise HttpError(
            400,
            "It looks like your text contains URLs. Please remove them and try again.",
        )

    # Supersede logic
    supersedes_pk = payload.supersedes
    superseded = None

    if not supersedes_pk:
        if asset.transcription_set.filter(supersedes=None).exists():
            structured_logger.warning(
                "API transcription save failed: open transcription exists",
                event_code="transcription_save_aborted",
                reason="Open transcription already exists",
                reason_code="already_exists",
                user=user,
                asset=asset,
            )
            raise HttpError(409, "An open transcription already exists")
    else:
        if asset.transcription_set.filter(supersedes=supersedes_pk).exists():
            structured_logger.warning(
                "API transcription save failed: already superseded",
                event_code="transcription_save_aborted",
                reason="Superseded transcription is invalid",
                reason_code="superseded_invalid",
                user=user,
                asset=asset,
                supersedes_pk=supersedes_pk,
            )
            raise HttpError(409, "This transcription has been superseded")

        try:
            superseded = asset.transcription_set.get(pk=supersedes_pk)
        except Transcription.DoesNotExist as err:
            structured_logger.warning(
                "API transcription save failed: supersedes not found",
                event_code="transcription_save_aborted",
                reason="Superseded transcription not found",
                reason_code="not_found",
                user=user,
                asset=asset,
                supersedes_pk=supersedes_pk,
            )
            raise HttpError(400, "Invalid supersedes value") from err

    ocr_originated = bool(
        superseded and (superseded.ocr_generated or superseded.ocr_originated)
    )

    transcription = Transcription(
        asset=asset,
        user=user,
        supersedes=superseded,
        text=payload.text,
        ocr_originated=ocr_originated,
    )
    transcription.full_clean()
    transcription.save()

    structured_logger.info(
        "API transcription save success",
        event_code="transcription_save_success",
        user=user,
        transcription=transcription,
    )

    return TranscriptionOut(
        id=transcription.pk,
        sent=time(),
        text=transcription.text,
        submission_url=reverse("api:submit_transcription", args=[transcription.pk]),
        asset=serialize_asset(asset, request),
        undo_available=asset.can_rollback()[0],
        redo_available=asset.can_rollforward()[0],
    )


@assets.post("/{asset_id}/transcriptions/ocr", response=TranscriptionOut, by_alias=True)
@atomic
def create_ocr_transcription(
    request: HttpRequest, asset_id: int, payload: OcrTranscriptionIn
) -> TranscriptionOut:
    """
    Create and save a new OCR-generated transcription for an asset.
    """
    asset = get_object_or_404(
        Asset.objects.published().select_related("item__project__campaign"),
        pk=asset_id,
    )
    user = request.user if not request.user.is_anonymous else get_anonymous_user()

    supersedes_pk = payload.supersedes
    language = payload.language

    structured_logger.info(
        "API OCR transcription generation start",
        event_code="ocr_generation_start",
        user=user,
        asset=asset,
        supersedes_pk=supersedes_pk,
        language=language,
    )

    # Determine superseded transcription
    superseded = None
    if supersedes_pk:
        superseded_qs = asset.transcription_set.filter(pk=supersedes_pk)
        if asset.transcription_set.filter(supersedes=supersedes_pk).exists():
            structured_logger.warning(
                "API OCR generation aborted: superseded transcription is invalid.",
                event_code="ocr_generation_aborted",
                reason="Superseded transcription is already superseded",
                reason_code="superseded_invalid",
                user=user,
                asset=asset,
                supersedes_pk=supersedes_pk,
            )
            raise HttpError(409, "This transcription has already been superseded")
        try:
            superseded = superseded_qs.get()
        except Transcription.DoesNotExist as err:
            structured_logger.warning(
                "API OCR generation aborted: superseded transcription not found.",
                event_code="ocr_generation_aborted",
                reason="Superseded transcription not found",
                reason_code="not_found",
                user=user,
                asset=asset,
                supersedes_pk=supersedes_pk,
            )
            raise HttpError(400, "Invalid supersedes value") from err
    else:
        # No transcription exists, so we create a blank one
        structured_logger.info(
            "No existing transcription; creating blank for OCR supersession",
            event_code="ocr_blank_supersede",
            user=user,
            asset=asset,
        )
        superseded = Transcription(
            asset=asset,
            user=get_anonymous_user(),
            text="",
        )
        superseded.full_clean()
        superseded.save()

        structured_logger.info(
            "Blank transcription created for OCR supersession",
            event_code="ocr_blank_transcription_created",
            user=user,
            transcription=superseded,
        )

    transcription_text = asset.get_ocr_transcript(language)

    transcription = Transcription(
        asset=asset,
        user=user,
        supersedes=superseded,
        text=transcription_text,
        ocr_generated=True,
        ocr_originated=True,
    )
    transcription.full_clean()
    transcription.save()

    structured_logger.info(
        "API OCR transcription successfully created",
        event_code="ocr_generation_success",
        user=user,
        transcription=transcription,
    )

    return TranscriptionOut(
        id=transcription.pk,
        sent=time(),
        text=transcription.text,
        submission_url=reverse("api:submit_transcription", args=[transcription.pk]),
        asset=serialize_asset(asset, request),
        undo_available=asset.can_rollback()[0],
        redo_available=asset.can_rollforward()[0],
    )


@assets.post(
    "/{asset_id}/transcriptions/rollback",
    response=TranscriptionOut,
    by_alias=True,
)
@atomic
def rollback(request: HttpRequest, asset_id: int) -> TranscriptionOut:
    """
    Restores the asset's transcription to the previous version in its history.

    Raises:
        HttpError: If no previous transcription exists to roll back to.
    """
    asset = get_object_or_404(Asset, pk=asset_id)
    user = request.user if not request.user.is_anonymous else get_anonymous_user()

    try:
        transcription = asset.rollback_transcription(user)
    except ValueError as e:
        structured_logger.warning(
            "Rollback failed: no previous transcription to revert to.",
            event_code="rollback_failed",
            reason_code="no_valid_target",
            reason=str(e),
            asset=asset,
            user=user,
        )
        raise HttpError(400, "No previous transcription available") from e

    structured_logger.info(
        "Rollback successfully performed.",
        event_code="rollback_success",
        user=user,
        transcription=transcription,
    )

    return TranscriptionOut(
        id=transcription.pk,
        sent=time(),
        text=transcription.text,
        submission_url=reverse("api:submit_transcription", args=[transcription.pk]),
        asset=serialize_asset(asset, request),
        undo_available=asset.can_rollback()[0],
        redo_available=asset.can_rollforward()[0],
    )


@assets.post(
    "/{asset_id}/transcriptions/rollforward",
    response=TranscriptionOut,
    by_alias=True,
)
@atomic
def rollforward(request: HttpRequest, asset_id: int) -> TranscriptionOut:
    """
    Restores the asset's transcription to the next version in its history.

    Raises:
        HttpError: If no future transcription exists to restore.
    """
    asset = get_object_or_404(Asset, pk=asset_id)
    user = request.user if not request.user.is_anonymous else get_anonymous_user()

    try:
        transcription = asset.rollforward_transcription(user)
    except ValueError as e:
        structured_logger.warning(
            "Rollforward failed: no transcription available to restore.",
            event_code="rollforward_failed",
            reason_code="no_valid_target",
            reason=str(e),
            asset=asset,
            user=user,
        )
        raise HttpError(400, "No transcription to restore") from e

    structured_logger.info(
        "Rollforward successfully performed.",
        event_code="rollforward_success",
        user=user,
        transcription=transcription,
    )

    return TranscriptionOut(
        id=transcription.pk,
        sent=time(),
        text=transcription.text,
        submission_url=reverse("api:submit_transcription", args=[transcription.pk]),
        asset=serialize_asset(asset, request),
        undo_available=asset.can_rollback()[0],
        redo_available=asset.can_rollforward()[0],
    )


transcriptions: Router = Router(tags=["transcriptions"])


@transcriptions.post("/{pk}/submit", response=TranscriptionOut, by_alias=True)
def submit_transcription(request: HttpRequest, pk: int) -> TranscriptionOut:
    """
    Submit a transcription for review (API version of legacy view).
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    asset = transcription.asset

    user = request.user if not request.user.is_anonymous else get_anonymous_user()

    structured_logger.info(
        "API transcription submit start",
        event_code="transcription_submit_start",
        user=user,
        transcription=transcription,
    )

    # Cannot submit already-submitted or superseded transcription
    is_superseded = asset.transcription_set.filter(supersedes=pk).exists()
    is_already_submitted = transcription.submitted and not transcription.rejected

    if is_superseded or is_already_submitted:
        structured_logger.warning(
            "API transcription submit failed: already submitted or superseded",
            event_code="transcription_submit_rejected",
            reason="Transcrition already submitted or superseded",
            reason_code="already_updated",
            user=user,
            transcription=transcription,
            is_superseded=is_superseded,
            is_already_submitted=is_already_submitted,
        )
        raise HttpError(
            400,
            "This transcription has already been updated. "
            "Reload the current status before continuing.",
        )

    # Perform the submission
    transcription.submitted = now()
    transcription.rejected = None
    transcription.full_clean()
    transcription.save()

    structured_logger.info(
        "API transcription submitted",
        event_code="transcription_submit_success",
        user=user,
        transcription=transcription,
    )

    return TranscriptionOut(
        id=transcription.pk,
        text=transcription.text,
        sent=time(),
        asset=serialize_asset(asset, request),
        undo_available=False,
        redo_available=False,
    )


@transcriptions.patch(
    "/{pk}/review",
    response=TranscriptionOut,
    by_alias=True,
)
def review_transcription(
    request: HttpRequest, pk: int, payload: ReviewIn
) -> TranscriptionOut:
    """
    Accept or reject a submitted transcription.

    Request Parameters:
        action (str): `"accept"` to accept or `"reject"` to reject.

    Raises:
        HttpError: If the action is invalid, the transcription was already
            reviewed, the user attempts a self-accept, or the review rate
            limit is exceeded.
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    asset = transcription.asset
    user = request.user if not request.user.is_anonymous else get_anonymous_user()

    # Temporary workaround to allow self-accepts for testing
    if payload.action == "accept" and transcription.user.pk == user.pk:
        user = ConcordiaUser.objects.latest("date_joined")
    # End workaround

    structured_logger.info(
        "API transcription review start",
        event_code="transcription_review_start",
        user=user,
        transcription_id=pk,
        action=payload.action,
    )

    if payload.action not in ("accept", "reject"):
        structured_logger.warning(
            "API review rejected: invalid action",
            event_code="transcription_review_rejected",
            reason="Invalid review action",
            reason_code="invalid_action",
            user=user,
            transcription_id=pk,
        )
        raise HttpError(400, "Invalid action")

    if transcription.accepted or transcription.rejected:
        structured_logger.warning(
            "API review rejected: already reviewed",
            event_code="transcription_review_rejected",
            reason="Transcription has already been reviewed",
            reason_code="already_reviewed",
            user=user,
            transcription=transcription,
        )
        raise HttpError(400, "This transcription has already been reviewed")

    if payload.action == "accept" and transcription.user.pk == user.pk:
        structured_logger.warning(
            "API review rejected: self-accept",
            event_code="transcription_review_rejected",
            reason="User attempted to accept their own transcription",
            reason_code="self_accept",
            user=request.user,
            transcription=transcription,
        )
        raise HttpError(400, "You cannot accept your own transcription")

    transcription.reviewed_by = user

    if payload.action == "accept":
        concordia_user = ConcordiaUser.objects.get(pk=user.pk)
        try:
            concordia_user.check_and_track_accept_limit(transcription)
        except RateLimitExceededError as err:
            structured_logger.warning(
                "API review rejected: rate limit exceeded",
                event_code="transcription_review_rejected",
                reason="User exceeded review rate limit",
                reason_code="rate_limit_exceeded",
                user=user,
                transcription=transcription,
            )
            raise HttpError(
                429, configuration_value("review_rate_limit_banner_message")
            ) from err
        transcription.accepted = now()
    else:
        transcription.rejected = now()

    transcription.full_clean()
    transcription.save()

    structured_logger.info(
        "API transcription review success",
        event_code="transcription_review_success",
        user=user,
        transcription=transcription,
        action=payload.action,
    )

    return TranscriptionOut(
        id=transcription.pk,
        text=transcription.text,
        sent=time(),
        asset=serialize_asset(asset, request),
        undo_available=False,
        redo_available=False,
    )


api.add_router("/assets", assets)
api.add_router("/transcriptions", transcriptions)
