from django.http import JsonResponse
from django.shortcuts import render

from concordia.utils import request_accepts_json


def ratelimit_view(request, exception=None):
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
