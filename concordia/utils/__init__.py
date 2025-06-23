from secrets import token_hex

from django.contrib.auth.models import User

from concordia.logging import ConcordiaLogger
from concordia.templatetags.concordia_media_tags import asset_media_url

__all__ = [
    "get_anonymous_user",
    "request_accepts_json",
    "get_or_create_reservation_token",
    "get_image_urls_from_asset",
]

structured_logger = ConcordiaLogger.get_logger(__name__)


def get_anonymous_user():
    """
    Get the user called "anonymous" if it exist. Create the user if it doesn't
    exist This is the default concordia user if someone is working on the site
    without logging in first.
    """

    try:
        return User.objects.get(username="anonymous")
    except User.DoesNotExist:
        return User.objects.create_user(username="anonymous")


def request_accepts_json(request):
    accept_header = request.headers.get("Accept", "*/*")

    return "application/json" in accept_header


def get_or_create_reservation_token(request):
    # Reservation tokens are 44 characters (22 bytes
    # converted into 44 hex digits) plus the user's
    # database id padded with leading zeroes until it's
    # at least 6 characters long
    if "reservation_token" not in request.session:
        request.session["reservation_token"] = token_hex(22)
        user = getattr(request, "user", None)
        if user is not None:
            uid = user.id
            if uid is None:
                uid = get_anonymous_user().id
            request.session["reservation_token"] += str(uid).zfill(6)
            structured_logger.info(
                "Reservation token created.",
                event_code="reservation_token_created",
                reservation_token=request.session["reservation_token"],
                user=user,
            )
    else:
        structured_logger.info(
            "Reservation token reused.",
            event_code="reservation_token_reused",
            reservation_token=request.session["reservation_token"],
        )
    return request.session["reservation_token"]


def get_image_urls_from_asset(asset):
    """
    Given an Asset, return a tuple containing the normalized full-size and
    thumbnail-size image URLs
    """

    image_url = asset_media_url(asset)
    if asset.download_url and "iiif" in asset.download_url:
        thumbnail_url = asset.download_url.replace(
            "http://tile.loc.gov", "https://tile.loc.gov"
        )
    else:
        thumbnail_url = image_url

    return image_url, thumbnail_url
