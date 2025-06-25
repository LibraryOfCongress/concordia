from typing import Optional

from django.shortcuts import get_object_or_404
from ninja import NinjaAPI, Router, Schema
from ninja.errors import HttpError

from concordia.models import Asset

api = NinjaAPI()


class AssetOut(Schema):
    id: int  # noqa: A003
    title: str


class TranscriptionIn(Schema):
    text: str
    supersedes: Optional[int] = None
    language: Optional[str] = None  # used only when OCR is involved


class TranscriptionOut(Schema):
    id: int  # noqa: A003
    asset_id: int
    status: str
    contributors: int


assets = Router(tags=["assets"])


@assets.get("/{asset_id}", response=AssetOut)
def asset_detail(request, asset_id: int):
    """GET /assets/{asset_id}/ – basic asset record."""
    asset = get_object_or_404(Asset, pk=asset_id)
    return {"id": asset.id, "title": asset.title}


@assets.post("/{asset_id}/transcriptions", response=TranscriptionOut)
def create_transcription(request, asset_id: int, payload: TranscriptionIn):
    """
    POST /assets/{id}/transcriptions/ – save a *new* draft transcription.

    *Supersession / validation / URL-checking logic to be ported here.*
    """
    # TODO: Port save_transcription() logic
    raise HttpError(501, "Not implemented yet")


@assets.post("/{asset_id}/transcriptions/ocr", response=TranscriptionOut)
def create_ocr_transcription(request, asset_id: int, payload: TranscriptionIn):
    """
    POST /assets/{id}/transcriptions/ocr/ – generate OCR transcription.

    Mirrors generate_ocr_transcription() view.
    """
    # TODO: Port generate_ocr_transcription() logic
    raise HttpError(501, "Not implemented yet")


@assets.post("/{asset_id}/transcriptions/rollback", response=TranscriptionOut)
def rollback(request, asset_id: int):
    """
    POST /assets/{id}/transcriptions/rollback/ – undo to the previous version.

    Mirrors rollback_transcription().
    """
    # TODO: Port rollback_transcription() logic
    raise HttpError(501, "Not implemented yet")


@assets.post("/{asset_id}/transcriptions/rollforward", response=TranscriptionOut)
def rollforward(request, asset_id: int):
    """
    POST /assets/{id}/transcriptions/rollforward/ – redo the last rollback.

    Mirrors rollforward_transcription().
    """
    # TODO: Port rollforward_transcription() logic
    raise HttpError(501, "Not implemented yet")


transcriptions = Router(tags=["transcriptions"])


@transcriptions.post("/{pk}/submit", response=TranscriptionOut)
def submit(request, pk: int):
    """
    POST /transcriptions/{pk}/submit/ – mark a draft as *submitted*.
    """
    # TODO: Port submit_transcription() logic
    raise HttpError(501, "Not implemented yet")


class ReviewIn(Schema):
    action: str  # "accept" or "reject"


@transcriptions.patch("/{pk}/review", response=TranscriptionOut)
def review(request, pk: int, payload: ReviewIn):
    """
    PATCH /transcriptions/{pk}/review/ – accept or reject.

    `payload.action` must be "accept" or "reject".
    """
    # TODO: Port review_transcription() logic
    raise HttpError(501, "Not implemented yet")


api.add_router("/assets", assets)
api.add_router("/transcriptions", transcriptions)
