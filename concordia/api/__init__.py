from typing import Optional

from django.conf import settings
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import HttpError

from concordia.models import (
    Asset,
    CardFamily,
    Guide,
    TranscriptionStatus,
    TutorialCard,
    UserAssetTagCollection,
)
from concordia.templatetags.concordia_media_tags import asset_media_url

from .api import CamelCaseAPI
from .schemas import CamelSchema

api = CamelCaseAPI()


class AssetOut(CamelSchema):
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


class TranscriptionIn(CamelSchema):
    text: str
    supersedes: Optional[int] = None
    language: Optional[str] = None  # used only when OCR is involved


class TranscriptionOut(CamelSchema):
    id: int  # noqa: A003
    asset_id: int
    status: str
    contributors: int


def serialize_asset(asset, request):
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

    return {
        "id": asset.id,
        "title": asset.title,
        "item_id": item.item_id,
        "project_slug": project.slug,
        "campaign_slug": campaign.slug,
        "transcription": transcription_out,
        "transcription_status": transcription_status,
        "activity_mode": activity_mode,
        "disable_ocr": disable_ocr,
        "current_asset_url": current_asset_url,
        "previous_asset_url": previous_asset_url,
        "next_asset_url": next_asset_url,
        "asset_navigation": asset_navigation,
        "image_url": image_url,
        "thumbnail_url": thumbnail_url,
        "tags": tags,
        "registered_contributors": asset.get_contributor_count(),
        "cards": cards,
        "guides": guides,
        "languages": list(settings.LANGUAGE_CODES.items()),
        "undo_available": undo_available,
        "redo_available": redo_available,
    }


assets = Router(tags=["assets"])


@assets.get(
    "/{campaign_slug}/{project_slug}/{item_id}/{asset_slug}/",
    response=AssetOut,
    by_alias=True,
)
def asset_detail_by_slugs(
    request,
    campaign_slug: str,
    project_slug: str,
    item_id: str,
    asset_slug: str,
):
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
def asset_detail(request, asset_id: int):
    """GET /assets/{asset_id}/ – basic asset record."""
    asset = get_object_or_404(
        Asset.objects.published().select_related("item__project__campaign"), pk=asset_id
    )
    return serialize_asset(asset, request)


@assets.post("/{asset_id}/transcriptions", response=TranscriptionOut, by_alias=True)
def create_transcription(request, asset_id: int, payload: TranscriptionIn):
    """
    POST /assets/{id}/transcriptions/ – save a *new* draft transcription.

    *Supersession / validation / URL-checking logic to be ported here.*
    """
    # TODO: Port save_transcription() logic
    raise HttpError(501, "Not implemented yet")


@assets.post("/{asset_id}/transcriptions/ocr", response=TranscriptionOut, by_alias=True)
def create_ocr_transcription(request, asset_id: int, payload: TranscriptionIn):
    """
    POST /assets/{id}/transcriptions/ocr/ – generate OCR transcription.

    Mirrors generate_ocr_transcription() view.
    """
    # TODO: Port generate_ocr_transcription() logic
    raise HttpError(501, "Not implemented yet")


@assets.post(
    "/{asset_id}/transcriptions/rollback", response=TranscriptionOut, by_alias=True
)
def rollback(request, asset_id: int):
    """
    POST /assets/{id}/transcriptions/rollback/ – undo to the previous version.

    Mirrors rollback_transcription().
    """
    # TODO: Port rollback_transcription() logic
    raise HttpError(501, "Not implemented yet")


@assets.post(
    "/{asset_id}/transcriptions/rollforward", response=TranscriptionOut, by_alias=True
)
def rollforward(request, asset_id: int):
    """
    POST /assets/{id}/transcriptions/rollforward/ – redo the last rollback.

    Mirrors rollforward_transcription().
    """
    # TODO: Port rollforward_transcription() logic
    raise HttpError(501, "Not implemented yet")


transcriptions = Router(tags=["transcriptions"])


@transcriptions.post("/{pk}/submit", response=TranscriptionOut, by_alias=True)
def submit(request, pk: int):
    """
    POST /transcriptions/{pk}/submit/ – mark a draft as *submitted*.
    """
    # TODO: Port submit_transcription() logic
    raise HttpError(501, "Not implemented yet")


class ReviewIn(CamelSchema):
    action: str  # "accept" or "reject"


@transcriptions.patch("/{pk}/review", response=TranscriptionOut, by_alias=True)
def review(request, pk: int, payload: ReviewIn):
    """
    PATCH /transcriptions/{pk}/review/ – accept or reject.

    `payload.action` must be "accept" or "reject".
    """
    # TODO: Port review_transcription() logic
    raise HttpError(501, "Not implemented yet")


api.add_router("/assets", assets)
api.add_router("/transcriptions", transcriptions)
