import logging
import re
from time import time
from typing import Union

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.transaction import atomic
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.timezone import now
from django.views.decorators.cache import cache_control, never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from concordia.exceptions import RateLimitExceededError
from concordia.logging import ConcordiaLogger
from concordia.models import (
    Asset,
    AssetTranscriptionReservation,
    ConcordiaUser,
    Tag,
    Transcription,
    UserAssetTagCollection,
)
from concordia.signals.signals import (
    reservation_obtained,
    reservation_released,
)
from concordia.utils import (
    get_anonymous_user,
    get_or_create_reservation_token,
)
from concordia.utils.constants import MESSAGE_LEVEL_NAMES, URL_REGEX
from configuration.utils import configuration_value
from exporter.utils import remove_unacceptable_characters

from .decorators import reserve_rate, validate_anonymous_user

logger = logging.getLogger(__name__)
structured_logger = ConcordiaLogger.get_logger(__name__)


@cache_control(private=True, max_age=settings.DEFAULT_PAGE_TTL)
@csrf_exempt
def ajax_session_status(request: HttpRequest) -> JsonResponse:
    """
    Return a JSON object describing the authenticated session state.

    If the user is authenticated, this includes a truncated username and
    navigational links to profile, logout, and admin pages (if staff or superuser).
    If the user is anonymous, returns an empty dictionary.

    Args:
        request (HttpRequest): The HTTP request initiating the session status check.

    Returns:
        response (JsonResponse): A dictionary containing either session information
            or empty data.

    Response Format - Success:
        - `username` (str): The first 15 characters of the user's username.
        - `links` (list[dict]): A list of links relevant to the user's session.
            - `title` (str): The label for the link (e.g., "Profile", "Logout").
            - `url` (str): The absolute URL for the link.

    Example:
        ```json
        // If the user is authenticated:
        {
            "username": "johndoe",
            "links": [
                {"title": "Profile", "url": "https://example.com/accounts/profile/"},
                {"title": "Logout", "url": "https://example.com/accounts/logout/"}
            ]
        }

        // If the user is anonymous:
        {}
        ```
    """
    user = request.user
    if user.is_anonymous:
        res = {}
    else:
        links = [
            {
                "title": "Profile",
                "type": "link",
                "url": request.build_absolute_uri(reverse("user-profile")),
            }
        ]
        if user.is_superuser or user.is_staff:
            links.append(
                {
                    "title": "Admin Area",
                    "type": "link",
                    "url": request.build_absolute_uri(reverse("admin:index")),
                }
            )
        links.append(
            {
                "title": "Logout",
                "type": "post",
                "url": request.build_absolute_uri(reverse("logout")),
                "fields": {"next": "/"},
            }
        )

        res = {"username": user.username[:15], "links": links}

    return JsonResponse(res)


@never_cache
@login_required
@csrf_exempt
def ajax_messages(request: HttpRequest) -> JsonResponse:
    """
    Return a JSON object containing the user's queued messages.

    Retrieves Django messages for the current request and formats them
    as a list of dictionaries, each containing the message text and its
    severity level.

    Requires the user to be authenticated.

    Args:
        request (HttpRequest): The request from the authenticated user.

    Returns:
        response (JsonResponse): A dictionary with a `messages` field containing
            a list of message entries.

    Response Format - Success:
        - `messages` (list[dict]): A list of user-visible messages.
            - `level` (str): The severity level of the message
              (e.g., "info", "warning", "error").
            - `message` (str): The text content of the message.

    Example:
        ```json
        {
            "messages": [
                {"level": "info", "message": "You have been logged out."},
                {"level": "warning", "message": "Your session is about to expire."}
            ]
        }
        ```
    """
    return JsonResponse(
        {
            "messages": [
                {"level": MESSAGE_LEVEL_NAMES[i.level], "message": i.message}
                for i in get_messages(request)
            ]
        }
    )


def get_transcription_superseded(
    asset: Asset, supersedes_pk: Union[int, str, None]
) -> Union[Transcription, JsonResponse, None]:
    """
    Determine the superseded transcription, if any, for a new transcription.

    If a valid `supersedes_pk` is provided, returns the corresponding transcription
    unless it has already been superseded. If no `supersedes_pk` is provided,
    checks whether the asset already has an open transcription.

    This helper may return an error response to be passed directly to the client,
    or a transcription object used when saving a new one.

    Args:
        asset (Asset): The asset the transcription is associated with.
        supersedes_pk (int or str or None): The primary key of the transcription
            being superseded, or `None` if this is the first transcription.

    Returns:
        response (Transcription or JsonResponse or None): A valid transcription,
            an error response, or `None`.

    Return Behavior:
        - If a valid transcription is found, a `Transcription` object is returned.
        - If the request is invalid or the transcription has already been superseded,
          a `JsonResponse` with an error is returned.
        - If there is no previous transcription to supersede, `None` is returned.

    Response Format - Error:
        - `error` (str): Explanation of why the transcription cannot be created.
            - "An open transcription already exists"
            - "This transcription has been superseded"
            - "Invalid supersedes value"

    Example:
        ```json
        {
            "error": "An open transcription already exists"
        }
        ```
    """
    structured_logger.info(
        "Checking for superseded transcription.",
        event_code="transcription_supersede_check_start",
        asset=asset,
        supersedes_pk=supersedes_pk,
    )
    if not supersedes_pk:
        if asset.transcription_set.filter(supersedes=None).exists():
            structured_logger.warning(
                "Open transcription already exists for asset.",
                event_code="transcription_supersede_check_failed",
                reason="An open transcription already exists",
                reason_code="already_exists",
                asset=asset,
            )
            return JsonResponse(
                {"error": "An open transcription already exists"}, status=409
            )
        else:
            superseded = None
    else:
        try:
            if asset.transcription_set.filter(supersedes=supersedes_pk).exists():
                structured_logger.warning(
                    "Transcription already superseded.",
                    event_code="transcription_supersede_check_failed",
                    reason="This transcription has been superseded",
                    reason_code="already_superseded",
                    asset=asset,
                    supersedes_pk=supersedes_pk,
                )
                return JsonResponse(
                    {"error": "This transcription has been superseded"}, status=409
                )

            try:
                superseded = asset.transcription_set.get(pk=supersedes_pk)
            except Transcription.DoesNotExist:
                structured_logger.warning(
                    "Supersedes transcription not found.",
                    event_code="transcription_supersede_check_failed",
                    reason="Invalid supersedes value",
                    reason_code="not_found",
                    asset=asset,
                    supersedes_pk=supersedes_pk,
                )
                return JsonResponse({"error": "Invalid supersedes value"}, status=400)
        except ValueError:
            structured_logger.warning(
                "Invalid supersedes value (non-integer).",
                event_code="transcription_supersede_check_failed",
                reason="Supersedes value must be an integer",
                reason_code="invalid_pk_format",
                asset=asset,
                supersedes_pk=supersedes_pk,
            )
            return JsonResponse({"error": "Invalid supersedes value"}, status=400)
        structured_logger.info(
            "Superseded transcription found.",
            event_code="transcription_supersede_check_success",
            asset=asset,
            supersedes_pk=supersedes_pk,
        )
    return superseded


@require_POST
@login_required
@atomic
@ratelimit(key="header:cf-connecting-ip", rate="1/m", block=settings.RATELIMIT_BLOCK)
def generate_ocr_transcription(
    request: HttpRequest, *, asset_pk: Union[int, str]
) -> JsonResponse:
    """
    Create and save a new OCR-generated transcription for an asset.

    If no prior transcription exists, creates a blank transcription to serve as
    the superseded record. Otherwise, the specified previous transcription is
    superseded by the new OCR transcription.

    Requires the user to be authenticated.

    Request Parameters:
        - `supersedes` (int or str, optional): The ID of the transcription being
          superseded.
        - `language` (str, optional): The language code to influence OCR output.

    Returns:
        response (JsonResponse): A dictionary describing the new transcription
            and asset status.

    Response Format - Success:
        - `id` (int): ID of the new transcription.
        - `sent` (float): UNIX timestamp when the transcription was created.
        - `submissionUrl` (str): URL to submit the transcription.
        - `text` (str): The OCR-generated transcription content.
        - `asset` (dict):
            - `id` (int): ID of the associated asset.
            - `status` (str): Current transcription status.
            - `contributors` (int): Number of users who have contributed.
        - `undo_available` (bool): Whether the user can roll back this transcription.
        - `redo_available` (bool): Whether the user can roll forward to another version.

    Example:
        ```json
        {
            "id": 123,
            "sent": 1716294920.927134,
            "submissionUrl": "/transcriptions/123/submit/",
            "text": "Detected OCR content...",
            "asset": {
                "id": 456,
                "status": "in_progress",
                "contributors": 2
            },
            "undo_available": true,
            "redo_available": false
        }
        ```
    """
    asset = get_object_or_404(Asset, pk=asset_pk)
    user = request.user

    supersedes_pk = request.POST.get("supersedes")
    language = request.POST.get("language", None)
    structured_logger.info(
        "Starting OCR transcription generation.",
        event_code="ocr_generation_start",
        user=user,
        asset=asset,
        supersedes_pk=supersedes_pk,
        language=language,
    )
    superseded = get_transcription_superseded(asset, supersedes_pk)
    if superseded:
        # If superseded is an HttpResponse, that means
        # this transcription has already been superseded, so
        # we won't run OCR and instead send back an error
        # Otherwise, we just have thr transcription the OCR
        # is gong to supersede, so we can continue
        if isinstance(superseded, HttpResponse):
            structured_logger.warning(
                "OCR generation aborted: superseded transcription is invalid.",
                event_code="ocr_generation_aborted",
                reason="Superseded transcription is invalid",
                reason_code="superseded_invalid",
                user=user,
                asset=asset,
            )
            return superseded
    else:
        # This means this is the first transcription on this asset.
        # To enable undoing of the OCR transcription, we create
        # an empty transcription for the OCR transcription to supersede
        structured_logger.info(
            "No existing transcription; creating empty one for OCR supersession.",
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
            "Blank superseded transcription created for OCR.",
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
        "OCR transcription successfully created.",
        event_code="ocr_generation_success",
        user=user,
        transcription=transcription,
    )

    return JsonResponse(
        {
            "id": transcription.pk,
            "sent": time(),
            "submissionUrl": reverse("submit-transcription", args=(transcription.pk,)),
            "text": transcription.text,
            "asset": {
                "id": transcription.asset.id,
                "status": transcription.asset.transcription_status,
                "contributors": transcription.asset.get_contributor_count(),
            },
            "undo_available": asset.can_rollback()[0],
            "redo_available": asset.can_rollforward()[0],
        },
        status=201,
    )


@require_POST
@validate_anonymous_user
@atomic
@ratelimit(key="header:cf-connecting-ip", rate="1/m", block=settings.RATELIMIT_BLOCK)
def rollback_transcription(
    request: HttpRequest, *, asset_pk: Union[int, str]
) -> JsonResponse:
    """
    Perform a rollback on the latest transcription for the given asset.

    Restores the asset's transcription to the previous version in its history.
    If rollback is not possible (e.g., no prior version exists), returns an error.

    Anonymous users are supported and handled via `get_anonymous_user()`. The caller
    must be validated via `validate_anonymous_user`.

    Args:
        request (HttpRequest): The POST request to initiate rollback.
        asset_pk (int or str): The primary key of the asset being rolled back.

    Returns:
        response (JsonResponse): A dictionary containing the restored transcription
            and asset status, or an error response if rollback fails.

    Response Format - Success:
        - `id` (int): ID of the restored transcription.
        - `sent` (float): UNIX timestamp of the response.
        - `submissionUrl` (str): URL to submit the transcription.
        - `text` (str): The restored transcription text.
        - `asset` (dict):
            - `id` (int): ID of the asset.
            - `status` (str): Current transcription status.
            - `contributors` (int): Number of users who contributed.
        - `message` (str): Confirmation message.
        - `undo_available` (bool): Whether rollback is possible again.
        - `redo_available` (bool): Whether rollforward is now available.

    Response Format - Error:
        - `error` (str): Explanation of the failure.
            - "No previous transcription available"

    Example:
        ```json
        {
            "id": 123,
            "sent": 1716295121.113204,
            "submissionUrl": "/transcriptions/123/submit/",
            "text": "Previous transcription text",
            "asset": {
                "id": 456,
                "status": "in_progress",
                "contributors": 1
            },
            "message": "Successfully rolled back transcription to previous version",
            "undo_available": false,
            "redo_available": true
        }
        ```
    """
    asset = get_object_or_404(Asset, pk=asset_pk)

    if request.user.is_anonymous:
        user = get_anonymous_user()
    else:
        user = request.user

    try:
        transcription = asset.rollback_transcription(user)
    except ValueError as e:
        logger.exception("No previous transcription available for rollback", exc_info=e)
        structured_logger.warning(
            "Rollback failed: no previous transcription to revert to.",
            event_code="rollback_failed",
            reason_code="no_valid_target",
            reason=str(e),
            asset=asset,
            user=user,
        )
        return JsonResponse(
            {"error": "No previous transcription available"}, status=400
        )

    structured_logger.info(
        "Rollback successfully performed.",
        event_code="rollback_success",
        user=user,
        transcription=transcription,
    )

    return JsonResponse(
        {
            "id": transcription.pk,
            "sent": time(),
            "submissionUrl": reverse("submit-transcription", args=(transcription.pk,)),
            "text": transcription.text,
            "asset": {
                "id": transcription.asset.id,
                "status": transcription.asset.transcription_status,
                "contributors": transcription.asset.get_contributor_count(),
            },
            "message": "Successfully rolled back transcription to previous version",
            "undo_available": transcription.asset.can_rollback()[0],
            "redo_available": transcription.asset.can_rollforward()[0],
        },
        status=201,
    )


@require_POST
@validate_anonymous_user
@atomic
@ratelimit(key="header:cf-connecting-ip", rate="1/m", block=settings.RATELIMIT_BLOCK)
def rollforward_transcription(
    request: HttpRequest, *, asset_pk: Union[int, str]
) -> JsonResponse:
    """
    Perform a rollforward to the transcription previously replaced by a rollback.

    Restores the asset's transcription to the next version in its history,
    if a valid rollforward target exists. If not, returns an error response.

    Anonymous users are supported and handled via `get_anonymous_user()`. The caller
    must be validated via `validate_anonymous_user`.

    Args:
        request (HttpRequest): The POST request to initiate rollforward.
        asset_pk (int or str): The primary key of the asset being rolled forward.

    Returns:
        response (JsonResponse): A dictionary containing the restored transcription
            and asset status, or an error response if rollforward fails.

    Response Format - Success:
        - `id` (int): ID of the restored transcription.
        - `sent` (float): UNIX timestamp of the response.
        - `submissionUrl` (str): URL to submit the transcription.
        - `text` (str): The restored transcription text.
        - `asset` (dict):
            - `id` (int): ID of the asset.
            - `status` (str): Current transcription status.
            - `contributors` (int): Number of users who contributed.
        - `message` (str): Confirmation message.
        - `undo_available` (bool): Whether rollback is now possible.
        - `redo_available` (bool): Whether another rollforward is possible.

    Response Format - Error:
        - `error` (str): Explanation of the failure.
            - "No transcription to restore"

    Example:
        ```json
        {
            "id": 124,
            "sent": 1716295243.029184,
            "submissionUrl": "/transcriptions/124/submit/",
            "text": "Next transcription text",
            "asset": {
                "id": 456,
                "status": "in_progress",
                "contributors": 1
            },
            "message": "Successfully restored transcription to next version",
            "undo_available": true,
            "redo_available": false
        }
        ```
    """
    asset = get_object_or_404(Asset, pk=asset_pk)

    if request.user.is_anonymous:
        user = get_anonymous_user()
    else:
        user = request.user

    try:
        transcription = asset.rollforward_transcription(user)
    except ValueError as e:
        logger.exception("No transcription available for rollforward", exc_info=e)
        structured_logger.warning(
            "Rollforward failed: no transcription available to restore.",
            event_code="rollforward_failed",
            reason_code="no_valid_target",
            reason=str(e),
            asset=asset,
            user=user,
        )
        return JsonResponse({"error": "No transcription to restore"}, status=400)

    structured_logger.info(
        "Rollforward successfully performed.",
        event_code="rollforward_success",
        user=user,
        transcription=transcription,
    )

    return JsonResponse(
        {
            "id": transcription.pk,
            "sent": time(),
            "submissionUrl": reverse("submit-transcription", args=(transcription.pk,)),
            "text": transcription.text,
            "asset": {
                "id": transcription.asset.id,
                "status": transcription.asset.transcription_status,
                "contributors": transcription.asset.get_contributor_count(),
            },
            "message": "Successfully restored transcription to next version",
            "undo_available": transcription.asset.can_rollback()[0],
            "redo_available": transcription.asset.can_rollforward()[0],
        },
        status=201,
    )


@require_POST
@validate_anonymous_user
@atomic
def save_transcription(
    request: HttpRequest, *, asset_pk: Union[int, str]
) -> JsonResponse:
    """
    Save a transcription draft for a given asset.

    Validates the transcription text for disallowed content (e.g., URLs).
    Non-printable characters are automatically removed before saving,
    using the shared exporter sanitization utilities. The view also checks
    for supersession rules. If valid, it creates and saves a new
    transcription associated with the current or anonymous user.

    Request Parameters:
        - `text` (str): The transcription text.
        - `supersedes` (int or str, optional): The ID of the transcription
          being superseded. Example: `"123"`

    Returns:
        response (JsonResponse): A dictionary describing the saved transcription
            and asset status, or an error response if validation fails.

    Response Format - Success:
        - `id` (int): ID of the saved transcription.
        - `sent` (float): UNIX timestamp of the response.
        - `submissionUrl` (str): URL to submit the transcription.
        - `asset` (dict):
            - `id` (int): ID of the associated asset.
            - `status` (str): Current transcription status.
            - `contributors` (int): Number of users who contributed.
        - `undo_available` (bool): Whether rollback is currently possible.
        - `redo_available` (bool): Whether rollforward is currently possible.

    Response Format - Error:
        - `error` (str): Explanation of the validation failure.
            - "It looks like your text contains URLs."
            - "An open transcription already exists"
            - "This transcription has been superseded"
            - "Invalid supersedes value"

    Example:
        ```json
        {
            "id": 125,
            "sent": 1716295310.743182,
            "submissionUrl": "/transcriptions/125/submit/",
            "text" : "Transcription text\r\nSecond line",
            "asset": {
                "id": 456,
                "status": "in_progress",
                "contributors": 1
            },
            "undo_available": true,
            "redo_available": false
        }
        ```
    """
    asset = get_object_or_404(Asset, pk=asset_pk)
    logger.info("Saving transcription for %s (%s)", asset, asset.id)

    if request.user.is_anonymous:
        user = get_anonymous_user()
    else:
        user = request.user

    structured_logger.info(
        "Starting transcription save.",
        event_code="transcription_save_start",
        user=user,
        asset=asset,
    )

    transcription_text = request.POST["text"]

    # Check whether this transcription text contains any URLs.
    # If so, ask the user to correct the transcription by removing the URLs.
    url_match = re.search(URL_REGEX, transcription_text)
    if url_match:
        structured_logger.warning(
            "Transcription save rejected due to URL in text.",
            event_code="transcription_save_rejected",
            reason="Transcription text contains URLs",
            reason_code="url_detected",
            user=user,
            asset=asset,
        )
        return JsonResponse(
            {
                "error": "It looks like your text contains URLs. "
                "Please remove the URLs and try again.",
                "error-code": "url_detected",
            },
            status=400,
        )

    # Sanitize the text by removing any unacceptable (non-printable) characters.
    # This leverages the shared exporter whitelist and logic so behavior remains
    # consistent across validation and export paths.
    transcription_text = remove_unacceptable_characters(transcription_text)

    supersedes_pk = request.POST.get("supersedes")
    superseded = get_transcription_superseded(asset, supersedes_pk)
    if superseded and isinstance(superseded, HttpResponse):
        logger.info("Transcription superseded")
        structured_logger.warning(
            "Superseded transcription is invalid; aborting save.",
            event_code="transcription_save_aborted",
            reason="Superseded transcription is invalid",
            reason_code="superseded_invalid",
            user=user,
            asset=asset,
        )
        return superseded

    if superseded and (superseded.ocr_generated or superseded.ocr_originated):
        ocr_originated = True
    else:
        ocr_originated = False

    transcription = Transcription(
        asset=asset,
        user=user,
        supersedes=superseded,
        text=transcription_text,
        ocr_originated=ocr_originated,
    )
    transcription.full_clean()
    transcription.save()
    logger.info("Transction %s saved", transcription.id)
    structured_logger.info(
        "Transcription saved successfully.",
        event_code="transcription_save_success",
        user=user,
        transcription=transcription,
    )

    return JsonResponse(
        {
            "id": transcription.pk,
            "sent": time(),
            "submissionUrl": reverse("submit-transcription", args=(transcription.pk,)),
            "text": transcription.text,
            "asset": {
                "id": transcription.asset.id,
                "status": transcription.asset.transcription_status,
                "contributors": transcription.asset.get_contributor_count(),
            },
            "undo_available": transcription.asset.can_rollback()[0],
            "redo_available": transcription.asset.can_rollforward()[0],
        },
        status=201,
    )


@require_POST
@validate_anonymous_user
def submit_transcription(request: HttpRequest, *, pk: Union[int, str]) -> JsonResponse:
    """
    Submit a transcription for review.

    Marks the transcription as submitted and clears any rejection state.
    Prevents submission if the transcription has already been accepted or
    superseded.

    Anonymous users are supported and handled via `get_anonymous_user()`. The caller
    must be validated via `validate_anonymous_user`.

    Args:
        request (HttpRequest): The POST request to submit the transcription.
        pk (int or str): The primary key of the transcription to submit.

    Returns:
        response (JsonResponse): A dictionary with the asset status and submission
            metadata, or an error response if submission is not allowed.

    Response Format - Success:
        - `id` (int): ID of the submitted transcription.
        - `sent` (float): UNIX timestamp of the response.
        - `asset` (dict):
            - `id` (int): ID of the associated asset.
            - `status` (str): Current transcription status.
            - `contributors` (int): Number of users who contributed.
        - `undo_available` (bool): Always `false` after submission.
        - `redo_available` (bool): Always `false` after submission.

    Response Format - Error:
        - `error` (str): Explanation of the submission failure.
            - "This transcription has already been updated."

    Example:
        ```json
        {
            "id": 126,
            "sent": 1716295421.019122,
            "asset": {
                "id": 456,
                "status": "submitted",
                "contributors": 1
            },
            "undo_available": false,
            "redo_available": false
        }
        ```
    """
    transcription = get_object_or_404(Transcription, pk=pk)
    asset = transcription.asset

    logger.info(
        "Transcription %s submitted for %s (%s)", transcription.id, asset, asset.id
    )

    is_superseded = transcription.asset.transcription_set.filter(supersedes=pk).exists()
    is_already_submitted = transcription.submitted and not transcription.rejected

    if is_already_submitted or is_superseded:
        logger.warning(
            (
                "Submit for review was attempted for invalid transcription "
                "record: submitted: %s pk: %d"
            ),
            str(transcription.submitted),
            pk,
        )
        structured_logger.warning(
            "Submission rejected: transcription already submitted or superseded.",
            event_code="transcription_submit_rejected",
            reason="Transcription already submitted or superseded",
            reason_code="already_updated",
            user=request.user,
            transcription=transcription,
        )

        return JsonResponse(
            {
                "error": "This transcription has already been updated."
                " Reload the current status before continuing."
            },
            status=400,
        )

    transcription.submitted = now()
    transcription.rejected = None
    transcription.full_clean()
    transcription.save()

    logger.info("Transcription %s successfully submitted", transcription.id)
    structured_logger.info(
        "Transcription submitted successfully.",
        event_code="transcription_submit_success",
        user=request.user,
        transcription=transcription,
    )

    return JsonResponse(
        {
            "id": transcription.pk,
            "sent": time(),
            "asset": {
                "id": transcription.asset.id,
                "status": transcription.asset.transcription_status,
                "contributors": transcription.asset.get_contributor_count(),
            },
            "undo_available": False,
            "redo_available": False,
        },
        status=200,
    )


@require_POST
@login_required
@never_cache
def review_transcription(request: HttpRequest, *, pk: Union[int, str]) -> JsonResponse:
    """
    Review and accept or reject a submitted transcription.

    Only non-authors may accept a transcription. Users are limited by a
    rate limit when accepting transcriptions. Review actions are rejected
    if the transcription has already been reviewed or is invalid.

    Args:
        request (HttpRequest): The POST request containing the review action.
        pk (int or str): The primary key of the transcription to review.

    Returns:
        response (JsonResponse): A dictionary with updated asset status and
            metadata, or an error response if the review fails.

    Response Format - Success:
        - `id` (int): ID of the reviewed transcription.
        - `sent` (float): UNIX timestamp of the response.
        - `asset` (dict):
            - `id` (int): ID of the associated asset.
            - `status` (str): Updated transcription status.
            - `contributors` (int): Number of users who contributed.

    Response Format - Error:
        - `error` (str): Explanation of the review failure.
            - "Invalid action"
            - "This transcription has already been reviewed"
            - "You cannot accept your own transcription"
            - Configuration-based rate limit messages

    Example:
        ```json
        {
            "id": 127,
            "sent": 1716295502.642184,
            "asset": {
                "id": 456,
                "status": "completed",
                "contributors": 2
            }
        }
        ```
    """
    action = request.POST.get("action")
    structured_logger.info(
        "Starting transcription review.",
        event_code="transcription_review_start",
        user=request.user,
        transcription_id=pk,
        action=action,
    )

    if action not in ("accept", "reject"):
        structured_logger.warning(
            "Transcription review failed: invalid action.",
            event_code="transcription_review_rejected",
            reason="Invalid review action",
            reason_code="invalid_action",
            user=request.user,
            transcription_id=pk,
            action=action,
        )
        return JsonResponse({"error": "Invalid action"}, status=400)

    transcription = get_object_or_404(Transcription, pk=pk)
    asset = transcription.asset

    logger.info(
        "Transcription %s reviewed (%s) for %s (%s)",
        transcription.id,
        action,
        asset,
        asset.id,
    )

    if transcription.accepted or transcription.rejected:
        structured_logger.warning(
            "Review rejected: transcription already reviewed.",
            event_code="transcription_review_rejected",
            reason="Transcription has already been reviewed",
            reason_code="already_reviewed",
            user=request.user,
            transcription=transcription,
        )
        return JsonResponse(
            {"error": "This transcription has already been reviewed"}, status=400
        )

    if transcription.user.pk == request.user.pk and action == "accept":
        logger.warning("Attempted self-acceptance for transcription %s", transcription)
        structured_logger.warning(
            "Review rejected: user attempted to accept their own transcription.",
            event_code="transcription_review_rejected",
            reason="User attempted to accept their own transcription",
            reason_code="self_accept",
            user=request.user,
            transcription=transcription,
        )
        return JsonResponse(
            {"error": "You cannot accept your own transcription"}, status=400
        )

    transcription.reviewed_by = request.user

    if action == "accept":
        concordia_user = ConcordiaUser.objects.get(id=request.user.id)
        try:
            concordia_user.check_and_track_accept_limit(transcription)
        except RateLimitExceededError:
            structured_logger.warning(
                "Review rejected: user exceeded review rate limit.",
                event_code="transcription_review_rejected",
                reason="User exceeded review rate limit",
                reason_code="rate_limit_exceeded",
                user=request.user,
                transcription=transcription,
            )
            return JsonResponse(
                {
                    "error": configuration_value("review_rate_limit_banner_message"),
                    "popupTitle": configuration_value("review_rate_limit_popup_title"),
                    "popupError": configuration_value(
                        "review_rate_limit_popup_message"
                    ),
                },
                status=429,
            )
        transcription.accepted = now()
    else:
        transcription.rejected = now()

    transcription.full_clean()
    transcription.save()

    logger.info("Transcription %s successfully reviewed (%s)", transcription.id, action)
    structured_logger.info(
        "Transcription review successful.",
        event_code="transcription_review_success",
        user=request.user,
        transcription=transcription,
        action=action,
    )

    return JsonResponse(
        {
            "id": transcription.pk,
            "sent": time(),
            "asset": {
                "id": transcription.asset.id,
                "status": transcription.asset.transcription_status,
                "contributors": transcription.asset.get_contributor_count(),
            },
        },
        status=200,
    )


@require_POST
@login_required
@atomic
def submit_tags(request: HttpRequest, *, asset_pk: Union[int, str]) -> JsonResponse:
    """
    Submit a new set of tags for an asset from the current user.

    Creates any new tags as needed and updates the user's tag collection
    for the asset. Removes tags that are no longer present in the submission.

    Args:
        request (HttpRequest): The POST request containing tag values.
        asset_pk (int or str): The primary key of the asset to tag.

    Returns:
        response (JsonResponse): A dictionary containing the updated user-specific
            and global tag lists for the asset.

    Response Format - Success:
        - `user_tags` (list[str]): Tags currently assigned to the asset by this user.
        - `all_tags` (list[str]): All tags currently applied to the asset by any user.

    Response Format - Error:
        - `error` (list[str]): Validation error messages for malformed/duplicate tags.

    Example:
        ```json
        {
            "user_tags": ["map", "handwritten"],
            "all_tags": ["handwritten", "map", "note"]
        }
        ```
    """
    asset = get_object_or_404(Asset, pk=asset_pk)
    structured_logger.info(
        "Starting tag submission.",
        event_code="tag_submit_start",
        user=request.user,
        asset=asset,
    )

    user_tags, created = UserAssetTagCollection.objects.get_or_create(
        asset=asset, user=request.user
    )

    tags = set(request.POST.getlist("tags"))
    existing_tags = Tag.objects.filter(value__in=tags)
    new_tag_values = tags.difference(i.value for i in existing_tags)
    new_tags = [Tag(value=i) for i in new_tag_values]
    try:
        for i in new_tags:
            i.full_clean()
    except ValidationError as exc:
        structured_logger.warning(
            "Tag submission rejected: validation error on new tags.",
            event_code="tag_submit_rejected",
            reason="Tag failed validation",
            reason_code="validation_error",
            user=request.user,
            asset=asset,
            errors=str(exc.messages),
        )
        return JsonResponse({"error": exc.messages}, status=400)

    Tag.objects.bulk_create(new_tags)

    # At this point we now have Tag objects for everything in the POSTed
    # request. We'll add anything which wasn't previously in this user's tag
    # collection and remove anything which is no longer present.

    all_submitted_tags = list(existing_tags) + new_tags
    existing_user_tags = user_tags.tags.all()

    for tag in all_submitted_tags:
        if tag not in existing_user_tags:
            user_tags.tags.add(tag)

    all_tags_qs = Tag.objects.filter(userassettagcollection__asset__pk=asset_pk)

    for tag in all_tags_qs:
        if tag not in all_submitted_tags:
            for collection in asset.userassettagcollection_set.all():
                collection.tags.remove(tag)

    all_tags = all_tags_qs.order_by("value")
    final_user_tags = user_tags.tags.order_by("value").values_list("value", flat=True)
    all_tags = all_tags.values_list("value", flat=True).distinct()

    structured_logger.info(
        "Tags submitted successfully.",
        event_code="tag_submit_success",
        user=request.user,
        asset=asset,
        user_tags=[tag.value for tag in user_tags.tags.all()],
    )

    return JsonResponse(
        {"user_tags": list(final_user_tags), "all_tags": list(all_tags)}
    )


@ratelimit(
    key="header:cf-connecting-ip", rate=reserve_rate, block=settings.RATELIMIT_BLOCK
)
@require_POST
@never_cache
def reserve_asset(request: HttpRequest, *, asset_pk: Union[int, str]) -> JsonResponse:
    """
    Attempt to reserve an asset for transcription by the current session.

    If no active reservation exists, creates a new one using the session's
    reservation token. If a reservation exists for this session, updates it.
    If the asset is reserved by another session, returns a conflict response.
    Handles reservation release if `release` is set in the request body.

    Request Parameters:
        - `release` (bool, optional): If present and true, releases the current
          reservation instead of acquiring or updating it. Example: `"true"`

    Returns:
        response (JsonResponse or HttpResponse): A dictionary indicating the
        reservation status and token, or an HTTP 408/409 response for timeout
        or conflict.

    Response Format - Success:
        - `asset_pk` (int): The ID of the reserved asset.
        - `reservation_token` (str): A unique identifier for the reservation session.

    Response Format - Error:
        - `408 Request Timeout`: The current session's reservation is tombstoned.
        - `409 Conflict`: The asset is actively reserved by another session.

    Example:
        ```json
        {
            "asset_pk": 789,
            "reservation_token": "abc123xyz"
        }
        ```
    """

    reservation_token = get_or_create_reservation_token(request)
    structured_logger.info(
        "Handling reservation request.",
        event_code="asset_reserve_start",
        asset_pk=asset_pk,
        reservation_token=reservation_token,
    )

    # If the browser is letting us know of a specific reservation release,
    # let it go even if it's within the grace period.
    if request.POST.get("release"):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM concordia_assettranscriptionreservation
                WHERE asset_id = %s and reservation_token = %s
                """,
                [asset_pk, reservation_token],
            )

        # We'll pass the message to the WebSocket listeners before returning it:
        msg = {"asset_pk": asset_pk, "reservation_token": reservation_token}
        logger.info("Releasing reservation with token %s", reservation_token)
        structured_logger.info(
            "Releasing asset reservation via client request.",
            event_code="asset_reserve_release",
            asset_pk=asset_pk,
            reservation_token=reservation_token,
        )
        reservation_released.send(sender="reserve_asset", **msg)
        return JsonResponse(msg)

    # We're relying on the database to meet our integrity requirements and since
    # this is called periodically we want to be fairly fast until we switch to
    # something like Redis.

    reservations = AssetTranscriptionReservation.objects.filter(
        asset_id__exact=asset_pk
    )

    # Default: pretend there is no activity on the asset
    is_it_already_mine = False
    am_i_tombstoned = False
    is_someone_else_tombstoned = False
    is_someone_else_active = False

    if reservations:
        for reservation in reservations:
            if reservation.tombstoned:
                if reservation.reservation_token == reservation_token:
                    am_i_tombstoned = True
                    logger.debug("I'm tombstoned %s", reservation_token)
                else:
                    is_someone_else_tombstoned = True
                    logger.debug(
                        "Someone else is tombstoned %s", reservation.reservation_token
                    )
            else:
                if reservation.reservation_token == reservation_token:
                    is_it_already_mine = True
                    logger.debug(
                        "I already have this active reservation %s", reservation_token
                    )
                if not is_it_already_mine:
                    is_someone_else_active = True
                    logger.info(
                        "Someone else has this active reservation %s",
                        reservation.reservation_token,
                    )

        if am_i_tombstoned:
            structured_logger.warning(
                "Reservation rejected: client is tombstoned.",
                event_code="asset_reserve_rejected",
                reason="Client reservation token is tombstoned",
                reason_code="tombstoned_self",
                asset_pk=asset_pk,
                reservation_token=reservation_token,
            )
            return HttpResponse(status=408)  # Request Timed Out

        if is_someone_else_active:
            structured_logger.warning(
                "Reservation rejected: asset is reserved by another client.",
                event_code="asset_reserve_rejected",
                reason="Asset is actively reserved by another session",
                reason_code="conflict_active_other",
                asset_pk=asset_pk,
                reservation_token=reservation_token,
            )
            return HttpResponse(status=409)  # Conflict

        if is_it_already_mine:
            # This user already has the reservation and it's not tombstoned
            structured_logger.info(
                "Reservation updated for client.",
                event_code="asset_reserve_updated",
                asset_pk=asset_pk,
                reservation_token=reservation_token,
            )
            msg = update_reservation(asset_pk, reservation_token)
            logger.debug("Updating reservation %s", reservation_token)

        if is_someone_else_tombstoned:
            # No reservations = no activity = go ahead and do an insert
            structured_logger.info(
                "Reservation acquired from tombstoned client.",
                event_code="asset_reserve_from_tombstone",
                asset_pk=asset_pk,
                reservation_token=reservation_token,
            )
            msg = obtain_reservation(asset_pk, reservation_token)
            logger.debug(
                "Obtaining reservation for %s from tombstoned user", reservation_token
            )
    else:
        # No reservations = no activity = go ahead and do an insert
        structured_logger.info(
            "Initial reservation acquired (no existing reservations).",
            event_code="asset_reserve_fresh",
            asset_pk=asset_pk,
            reservation_token=reservation_token,
        )
        msg = obtain_reservation(asset_pk, reservation_token)
        logger.debug("No activity, just get the reservation %s", reservation_token)

    return JsonResponse(msg)


def update_reservation(
    asset_pk: Union[int, str], reservation_token: str
) -> dict[str, Union[int, str]]:
    """
    Update the timestamp on an existing active reservation for an asset.

    Refreshes the reservation's `updated_on` field to extend its validity
    and emits the `reservation_obtained` signal.

    Args:
        asset_pk (int or str): The primary key of the reserved asset.
        reservation_token (str): The session's reservation token.

    Returns:
        response (dict): A dictionary confirming the updated reservation state.

    Response Format - Success:
        - `asset_pk` (int): The ID of the reserved asset.
        - `reservation_token` (str): The reservation token used by the session.

    Example:
        ```json
        {
            "asset_pk": 789,
            "reservation_token": "abc123xyz"
        }
        ```
    """
    structured_logger.info(
        "Attempting to update reservation timestamp.",
        event_code="reservation_update_start",
        asset_pk=asset_pk,
        reservation_token=reservation_token,
    )
    with connection.cursor() as cursor:
        cursor.execute(
            """
        UPDATE concordia_assettranscriptionreservation AS atr
            SET updated_on = current_timestamp
            WHERE (
                atr.asset_id = %s
                AND atr.reservation_token = %s
                AND atr.tombstoned != TRUE
                )
        """.strip(),
            [asset_pk, reservation_token],
        )
    structured_logger.info(
        "Reservation update SQL executed.",
        event_code="reservation_update_sql_executed",
        asset_pk=asset_pk,
        reservation_token=reservation_token,
    )
    # We'll pass the message to the WebSocket listeners before returning it:
    msg = {"asset_pk": asset_pk, "reservation_token": reservation_token}
    reservation_obtained.send(sender="reserve_asset", **msg)
    structured_logger.info(
        "Reservation update completed; signal dispatched.",
        event_code="reservation_update_success",
        asset_pk=asset_pk,
        reservation_token=reservation_token,
    )
    return msg


def obtain_reservation(
    asset_pk: Union[int, str], reservation_token: str
) -> dict[str, Union[int, str]]:
    """
    Create a new reservation entry for an asset.

    Inserts a new reservation row in the database for the given asset and
    session token. Emits the `reservation_obtained` signal to notify listeners.

    Args:
        asset_pk (int or str): The primary key of the asset to reserve.
        reservation_token (str): The session's reservation token.

    Returns:
        response (dict): A dictionary confirming the newly obtained reservation.

    Response Format - Success:
        - `asset_pk` (int): The ID of the reserved asset.
        - `reservation_token` (str): The reservation token used by the session.

    Example:
        ```json
        {
            "asset_pk": 789,
            "reservation_token": "abc123xyz"
        }
        ```
    """
    structured_logger.info(
        "Attempting to create new reservation.",
        event_code="reservation_obtain_start",
        asset_pk=asset_pk,
        reservation_token=reservation_token,
    )
    with connection.cursor() as cursor:
        cursor.execute(
            """
        INSERT INTO concordia_assettranscriptionreservation AS atr
            (asset_id, reservation_token, tombstoned, created_on,
            updated_on)
            VALUES (%s, %s, FALSE, current_timestamp,
            current_timestamp)
        """.strip(),
            [asset_pk, reservation_token],
        )
    structured_logger.info(
        "Reservation INSERT executed successfully.",
        event_code="reservation_insert_success",
        asset_pk=asset_pk,
        reservation_token=reservation_token,
    )
    # We'll pass the message to the WebSocket listeners before returning it:
    msg = {"asset_pk": asset_pk, "reservation_token": reservation_token}
    reservation_obtained.send(sender="reserve_asset", **msg)
    structured_logger.info(
        "Reservation successfully obtained; signal dispatched.",
        event_code="reservation_obtain_success",
        asset_pk=asset_pk,
        reservation_token=reservation_token,
    )
    return msg
