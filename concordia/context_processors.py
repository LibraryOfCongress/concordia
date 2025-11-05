from typing import Any, Dict

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest


def system_configuration(request: HttpRequest) -> Dict[str, Any]:
    """
    Expose selected settings to templates via the default context.

    Adds the following keys:
      * SENTRY_FRONTEND_DSN: Front-end DSN string or None
      * CONCORDIA_ENVIRONMENT: Current environment label
      * S3_BUCKET_NAME: Bucket name for public media or None
      * APPLICATION_VERSION: Deployed version string or None

    Args:
        request:
            The current HTTP request. Included for the context processor
            signature; it is not used.

    Returns:
        dict: Mapping of configuration keys to values for templates.
    """
    return {
        "SENTRY_FRONTEND_DSN": getattr(settings, "SENTRY_FRONTEND_DSN", None),
        "CONCORDIA_ENVIRONMENT": settings.CONCORDIA_ENVIRONMENT,
        "S3_BUCKET_NAME": getattr(settings, "S3_BUCKET_NAME", None),
        "APPLICATION_VERSION": getattr(settings, "APPLICATION_VERSION", None),
    }


def site_navigation(request: HttpRequest) -> Dict[str, Any]:
    """
    Provide navigation helpers derived from the request.

    Adds:
      * VIEW_NAME: The resolved Django view name if available
      * VIEW_NAME_FOR_CSS: VIEW_NAME with ``:`` replaced by ``--`` for CSS
      * PATH_LEVEL_N: Each path segment by position, 1-indexed

    Example:
        For ``/campaigns/demo/item/123/`` this yields::

            {
                "PATH_LEVEL_1": "campaigns",
                "PATH_LEVEL_2": "demo",
                "PATH_LEVEL_3": "item",
                "PATH_LEVEL_4": "123",
            }

    Args:
        request:
            The current HTTP request used to derive view and path data.

    Returns:
        dict: Mapping of helper keys to values for templates.
    """
    data: Dict[str, Any] = {}

    if request.resolver_match:
        data["VIEW_NAME"] = request.resolver_match.view_name
        data["VIEW_NAME_FOR_CSS"] = data["VIEW_NAME"].replace(":", "--")

    path_components = request.path.strip("/").split("/")
    for i, component in enumerate(path_components, start=1):
        data["PATH_LEVEL_%d" % i] = component

    return data


def maintenance_mode_frontend_available(request: HttpRequest) -> Dict[str, Any]:
    """
    Expose a flag indicating front-end maintenance mode readiness.

    Reads the ``maintenance_mode_frontend_available`` cache key and returns a
    boolean under the same name in the template context.

    Args:
        request:
            The current HTTP request. Included for the context processor
            signature; it is not used.

    Returns:
        dict: ``{"maintenance_mode_frontend_available": bool}``.
    """
    value = cache.get("maintenance_mode_frontend_available", False)
    return {"maintenance_mode_frontend_available": value}


def request_id_context(request: HttpRequest) -> Dict[str, Any]:
    """
    Expose the per-request identifier, if present.

    Relies on middleware attaching ``request.request_id``. Returns the value
    or ``None`` if absent.

    Args:
        request:
            The current HTTP request holding ``request_id`` if set.

    Returns:
        dict: ``{"request_id": str | None}``.
    """
    return {"request_id": getattr(request, "request_id", None)}
