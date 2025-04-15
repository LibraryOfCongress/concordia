import logging
import re
from time import time

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.transaction import atomic
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.timezone import now
from django.views.decorators.cache import cache_control, never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from concordia.exceptions import RateLimitExceededError
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
from configuration.utils import configuration_value

from .decorators import reserve_rate, validate_anonymous_user
from .utils import MESSAGE_LEVEL_NAMES, URL_REGEX

logger = logging.getLogger(__name__)


@cache_control(private=True, max_age=settings.DEFAULT_PAGE_TTL)
@csrf_exempt
def ajax_session_status(request):
    """
    Returns the user-specific information which would otherwise make many pages
    uncacheable
    """

    user = request.user
    if user.is_anonymous:
        res = {}
    else:
        links = [
            {
                "title": "Profile",
                "url": request.build_absolute_uri(reverse("user-profile")),
            }
        ]
        if user.is_superuser or user.is_staff:
            links.append(
                {
                    "title": "Admin Area",
                    "url": request.build_absolute_uri(reverse("admin:index")),
                }
            )
        links.append(
            {
                "title": "Logout",
                "url": request.build_absolute_uri(reverse("logout")),
            }
        )

        res = {"username": user.username[:15], "links": links}

    return JsonResponse(res)


@never_cache
@login_required
@csrf_exempt
def ajax_messages(request):
    """
    Returns any messages queued for the current user
    """

    return JsonResponse(
        {
            "messages": [
                {"level": MESSAGE_LEVEL_NAMES[i.level], "message": i.message}
                for i in get_messages(request)
            ]
        }
    )


def get_transcription_superseded(asset, supersedes_pk):
    if not supersedes_pk:
        if asset.transcription_set.filter(supersedes=None).exists():
            return JsonResponse(
                {"error": "An open transcription already exists"}, status=409
            )
        else:
            superseded = None
    else:
        try:
            if asset.transcription_set.filter(supersedes=supersedes_pk).exists():
                return JsonResponse(
                    {"error": "This transcription has been superseded"}, status=409
                )

            try:
                superseded = asset.transcription_set.get(pk=supersedes_pk)
            except Transcription.DoesNotExist:
                return JsonResponse({"error": "Invalid supersedes value"}, status=400)
        except ValueError:
            return JsonResponse({"error": "Invalid supersedes value"}, status=400)
    return superseded


@require_POST
@login_required
@atomic
@ratelimit(key="header:cf-connecting-ip", rate="1/m", block=settings.RATELIMIT_BLOCK)
def generate_ocr_transcription(request, *, asset_pk):
    asset = get_object_or_404(Asset, pk=asset_pk)
    user = request.user

    supersedes_pk = request.POST.get("supersedes")
    language = request.POST.get("language", None)
    superseded = get_transcription_superseded(asset, supersedes_pk)
    if superseded:
        # If superseded is an HttpResponse, that means
        # this transcription has already been superseded, so
        # we won't run OCR and instead send back an error
        # Otherwise, we just have thr transcription the OCR
        # is gong to supersede, so we can continue
        if isinstance(superseded, HttpResponse):
            return superseded
    else:
        # This means this is the first transcription on this asset.
        # To enable undoing of the OCR transcription, we create
        # an empty transcription for the OCR transcription to supersede
        superseded = Transcription(
            asset=asset,
            user=get_anonymous_user(),
            text="",
        )
        superseded.full_clean()
        superseded.save()

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
def rollback_transcription(request, *, asset_pk):
    asset = get_object_or_404(Asset, pk=asset_pk)

    if request.user.is_anonymous:
        user = get_anonymous_user()
    else:
        user = request.user

    try:
        transcription = asset.rollback_transcription(user)
    except ValueError as e:
        logger.exception("No previous transcription available for rollback", exc_info=e)
        return JsonResponse(
            {"error": "No previous transcription available"}, status=400
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
def rollforward_transcription(request, *, asset_pk):
    asset = get_object_or_404(Asset, pk=asset_pk)

    if request.user.is_anonymous:
        user = get_anonymous_user()
    else:
        user = request.user

    try:
        transcription = asset.rollforward_transcription(user)
    except ValueError as e:
        logger.exception("No transcription available for rollforward", exc_info=e)
        return JsonResponse({"error": "No transcription to restore"}, status=400)

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
def save_transcription(request, *, asset_pk):
    asset = get_object_or_404(Asset, pk=asset_pk)
    logger.info("Saving transcription for %s (%s)", asset, asset.id)

    if request.user.is_anonymous:
        user = get_anonymous_user()
    else:
        user = request.user

    # Check whether this transcription text contains any URLs
    # If so, ask the user to correct the transcription by removing the URLs
    transcription_text = request.POST["text"]
    url_match = re.search(URL_REGEX, transcription_text)
    if url_match:
        return JsonResponse(
            {
                "error": "It looks like your text contains URLs. "
                "Please remove the URLs and try again."
            },
            status=400,
        )

    supersedes_pk = request.POST.get("supersedes")
    superseded = get_transcription_superseded(asset, supersedes_pk)
    if superseded and isinstance(superseded, HttpResponse):
        logger.info("Transcription superseded")
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

    return JsonResponse(
        {
            "id": transcription.pk,
            "sent": time(),
            "submissionUrl": reverse("submit-transcription", args=(transcription.pk,)),
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
def submit_transcription(request, *, pk):
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
def review_transcription(request, *, pk):
    action = request.POST.get("action")

    if action not in ("accept", "reject"):
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
        return JsonResponse(
            {"error": "This transcription has already been reviewed"}, status=400
        )

    if transcription.user.pk == request.user.pk and action == "accept":
        logger.warning("Attempted self-acceptance for transcription %s", transcription)
        return JsonResponse(
            {"error": "You cannot accept your own transcription"}, status=400
        )

    transcription.reviewed_by = request.user

    if action == "accept":
        concordia_user = ConcordiaUser.objects.get(id=request.user.id)
        try:
            concordia_user.check_and_track_accept_limit(transcription)
        except RateLimitExceededError:
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
def submit_tags(request, *, asset_pk):
    asset = get_object_or_404(Asset, pk=asset_pk)

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

    return JsonResponse(
        {"user_tags": list(final_user_tags), "all_tags": list(all_tags)}
    )


@ratelimit(
    key="header:cf-connecting-ip", rate=reserve_rate, block=settings.RATELIMIT_BLOCK
)
@require_POST
@never_cache
def reserve_asset(request, *, asset_pk):
    """
    Receives an asset PK and attempts to create/update a reservation for it

    Returns JSON message with reservation token on success

    Returns HTTP 409 when the record is in use
    """

    reservation_token = get_or_create_reservation_token(request)

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
            return HttpResponse(status=408)  # Request Timed Out

        if is_someone_else_active:
            return HttpResponse(status=409)  # Conflict

        if is_it_already_mine:
            # This user already has the reservation and it's not tombstoned
            msg = update_reservation(asset_pk, reservation_token)
            logger.debug("Updating reservation %s", reservation_token)

        if is_someone_else_tombstoned:
            msg = obtain_reservation(asset_pk, reservation_token)
            logger.debug(
                "Obtaining reservation for %s from tombstoned user", reservation_token
            )

    else:
        # No reservations = no activity = go ahead and do an insert
        msg = obtain_reservation(asset_pk, reservation_token)
        logger.debug("No activity, just get the reservation %s", reservation_token)

    return JsonResponse(msg)


def update_reservation(asset_pk, reservation_token):
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
    # We'll pass the message to the WebSocket listeners before returning it:
    msg = {"asset_pk": asset_pk, "reservation_token": reservation_token}
    reservation_obtained.send(sender="reserve_asset", **msg)
    return msg


def obtain_reservation(asset_pk, reservation_token):
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
    # We'll pass the message to the WebSocket listeners before returning it:
    msg = {"asset_pk": asset_pk, "reservation_token": reservation_token}
    reservation_obtained.send(sender="reserve_asset", **msg)
    return msg
