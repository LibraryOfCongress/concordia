from secrets import token_hex

from django.contrib.auth.models import User


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
    accept_header = request.META.get("HTTP_ACCEPT", "*/*")

    return "application/json" in accept_header


def get_or_create_reservation_token(request):
    if "reservation_token" not in request.session:
        request.session["reservation_token"] = token_hex(25)
    return request.session["reservation_token"]
