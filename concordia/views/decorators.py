from functools import wraps
from time import time

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.cache import cache_control, never_cache
from django.views.decorators.vary import vary_on_headers

from concordia.forms import TurnstileForm


def default_cache_control(view_function):
    """
    Decorator for views which use our default cache control policy for public pages
    """

    @vary_on_headers("Accept-Encoding")
    @cache_control(public=True, max_age=settings.DEFAULT_PAGE_TTL)
    @wraps(view_function)
    def inner(*args, **kwargs):
        return view_function(*args, **kwargs)

    return inner


def user_cache_control(view_function):
    """
    Decorator for views that vary by user
    Only applicable if the user is authenticated
    """

    @vary_on_headers("Accept-Encoding", "Cookie")
    @cache_control(public=True, max_age=settings.DEFAULT_PAGE_TTL)
    @wraps(view_function)
    def inner(*args, **kwargs):
        return view_function(*args, **kwargs)

    return inner


def validate_anonymous_user(view):
    @wraps(view)
    @never_cache
    def inner(request, *args, **kwargs):
        if not request.user.is_authenticated and request.method == "POST":
            # First check if the user has already been validated within the time limit
            # If so, validation can be skipped
            turnstile_last_validated = request.session.get(
                "turnstile_last_validated", 0
            )
            age = time() - turnstile_last_validated
            if age > settings.ANONYMOUS_USER_VALIDATION_INTERVAL:
                form = TurnstileForm(request.POST)
                if not form.is_valid():
                    return JsonResponse(
                        {"error": "Unable to validate. " "Please try again or login."},
                        status=401,
                    )
                else:
                    # User has been validated, so we'll cache the time in their session
                    request.session["turnstile_last_validated"] = time()

        return view(request, *args, **kwargs)

    return inner


def reserve_rate(group, request):
    # `group` is the group of rate limits to count together
    # It defaults to the dotted name of the view, so each
    # view is its own unique group
    return None if request.user.is_authenticated else "100/m"
