from collections.abc import Callable
from functools import wraps
from time import time

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import cache_control, never_cache
from django.views.decorators.vary import vary_on_headers

from concordia.forms import TurnstileForm
from concordia.logging import ConcordiaLogger
from configuration.utils import configuration_value
from configuration.validation import validate_rate

structured_logger = ConcordiaLogger.get_logger(__name__)


def default_cache_control(view_function: Callable) -> Callable:
    """
    Decorator that applies default cache control headers to public-facing views.

    This decorator sets `Cache-Control: public` with a max-age defined in the
    `DEFAULT_PAGE_TTL` Django setting. It also varies the response by the
    `Accept-Encoding` header.

    Args:
        view_function (Callable): The view function to decorate.

    Returns:
        Callable: The wrapped view function with cache control headers applied.
    """

    @vary_on_headers("Accept-Encoding")
    @cache_control(public=True, max_age=settings.DEFAULT_PAGE_TTL)
    @wraps(view_function)
    def inner(*args, **kwargs):
        return view_function(*args, **kwargs)

    return inner


def user_cache_control(view_function: Callable) -> Callable:
    """
    Decorator that applies cache control headers for views varying by session.

    This decorator is intended for views that may return different content
    based on whether the user is authenticated. It sets
    `Cache-Control: public` with the `DEFAULT_PAGE_TTL` setting and varies
    the response by both `Accept-Encoding` and `Cookie` headers.

    Args:
        view_function (Callable): The view function to decorate.

    Returns:
        Callable: The wrapped view function with user-aware cache control
            headers.
    """

    @vary_on_headers("Accept-Encoding", "Cookie")
    @cache_control(public=True, max_age=settings.DEFAULT_PAGE_TTL)
    @wraps(view_function)
    def inner(*args, **kwargs):
        return view_function(*args, **kwargs)

    return inner


def validate_anonymous_user(view: Callable) -> Callable:
    """
    Decorator that applies anonymous user validation for `POST` requests.

    If the user is unauthenticated and submits a `POST` request, this
    decorator checks whether the user has recently passed Turnstile
    validation. If not, it validates the request using a `TurnstileForm`.
    Failing validation returns a 401 JSON response.

    The timestamp of a successful validation is stored in the user session
    to avoid re-validating within the configured interval.

    Args:
        view (Callable): The view function to wrap.

    Returns:
        Callable: The wrapped view function with anonymous user validation
            logic.
    """

    @wraps(view)
    @never_cache
    def inner(request, *args, **kwargs):
        if not request.user.is_authenticated and request.method == "POST":
            # First check if the user has already been validated within the
            # time limit. If so, validation can be skipped.
            turnstile_last_validated = request.session.get(
                "turnstile_last_validated", 0
            )
            age = time() - turnstile_last_validated
            if age > settings.ANONYMOUS_USER_VALIDATION_INTERVAL:
                form = TurnstileForm(request.POST)
                if not form.is_valid():
                    return JsonResponse(
                        {
                            "error": (
                                "Unable to validate. Please try again or " "login."
                            )
                        },
                        status=401,
                    )
                else:
                    # User has been validated, so cache the time in the
                    # session.
                    request.session["turnstile_last_validated"] = time()

        return view(request, *args, **kwargs)

    return inner


def reserve_rate(group: str, request: HttpRequest) -> str | None:
    """
    Determine the rate limit value for a request.

    This helper is used to control throttling behavior. If the user is
    anonymous, it returns a fixed rate limit string, for example "100/m".
    Authenticated users are not rate-limited and it returns `None`.

    The `group` parameter controls how rate limits are grouped. It defaults
    to the dotted name of the view so each view is treated as its own rate
    limit bucket unless explicitly overridden.

    Args:
        group (str): Group name used to bucket rate limits. Defaults to the
            dotted view name if not set manually.
        request (HttpRequest): The incoming HTTP request.

    Returns:
        str | None: A rate string such as "100/m" for anonymous users, or
            `None` otherwise.
    """
    return None if request.user.is_authenticated else "100/m"


def next_asset_rate(group: str, request: HttpRequest) -> str | None:
    """
    Determine the rate limit value for a next-asset request.

    If the user is anonymous, this helper returns a rate limit string from
    the `next_asset_rate_limit` configuration value, for example "4/m".
    Authenticated users are not rate-limited and it returns `None`.

    The `group` parameter controls how rate limits are grouped. It is used
    internally by `django-ratelimit`. It could be used to return different
    rate limits based on the group, but that is not needed currently.

    Args:
        group (str): Group name used to bucket rate limits. Defaults to the
            dotted view name if not set manually.
        request (HttpRequest): The incoming HTTP request.

    Returns:
        str | None: A rate string such as "4/m" for anonymous users, or
            `None` otherwise.
    """
    if request.user.is_authenticated:
        return None
    try:
        rate_limit = configuration_value("next_asset_rate_limit")
        return validate_rate(rate_limit)
    except (ObjectDoesNotExist, ValidationError) as exc:
        structured_logger.warning(
            "Falling back to default next-asset rate limit.",
            event_code="next_asset_rate_config_fallback",
            reason="Could not load or validate configured rate limit",
            reason_code="config_missing_or_invalid",
            group=group,
            default_rate="4/m",
            user=request.user,
            error_type=exc.__class__.__name__,
            error=str(exc),
        )
        return "4/m"
