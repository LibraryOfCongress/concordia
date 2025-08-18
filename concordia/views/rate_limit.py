from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from concordia.utils import request_accepts_json


def ratelimit_view(
    request: HttpRequest, exception: Exception | None = None
) -> HttpResponse:
    """
    Handles requests blocked due to rate limiting (HTTP 429).

    Determines whether to return a JSON or HTML response based on the request headers.
    Adds a `Retry-After` header instructing clients to wait 15 minutes before retrying.

    Args:
        request (HttpRequest): The incoming request that triggered the rate limit.
        exception (Exception | None): The exception that caused the view to trigger,
            if available.

    Returns:
        HttpResponse: A JSON or HTML 429 response with a retry header.
    """
    status_code = 429

    ctx = {
        "error": "You have been rate-limited. Please try again later.",
        "status": status_code,
    }

    if exception is not None:
        ctx["exception"] = str(exception)

    if request.headers.get(
        "x-requested-with"
    ) == "XMLHttpRequest" or request_accepts_json(request):
        response = JsonResponse(ctx, status=status_code)
    else:
        response = render(request, "429.html", context=ctx, status=status_code)

    response["Retry-After"] = 15 * 60

    return response
