"""
Maintenance-mode helpers for conditional frontend availability.

This module wraps ``maintenance_mode.http.need_maintenance_response`` to allow
staff or superusers limited frontend access during maintenance when a cache
flag is set.
"""

from django.core.cache import cache
from django.http import HttpRequest
from maintenance_mode.http import (
    need_maintenance_response as base_need_maintenance_response,
)


def _need_maintenence_frontend(request: HttpRequest) -> bool | None:
    """
    Optionally allow frontend access for privileged users during maintenance.

    When the cache key ``maintenance_mode_frontend_available`` is truthy and the
    request has an authenticated user who is staff or a superuser, return
    ``False`` to indicate maintenance should not block the response. Otherwise
    return ``None`` to defer to the default logic.

    Args:
        request: Current HTTP request.

    Returns:
        False to allow access, None to defer to default handling.
    """
    if not hasattr(request, "user"):
        return None

    user = request.user

    frontend_available = cache.get("maintenance_mode_frontend_available", False)
    if frontend_available and (user.is_staff or user.is_superuser):
        return False
    return None


def need_maintenance_response(request: HttpRequest) -> bool:
    """
    Determine whether maintenance mode should block this request.

    First delegates to the upstream maintenance-mode check. If it indicates that
    maintenance applies, call ``_need_maintenence_frontend`` to allow privileged
    access when enabled via cache. Returns a boolean suitable for the middleware.

    Args:
        request: Current HTTP request.

    Returns:
        True if maintenance mode should block the request, else False.
    """
    value = base_need_maintenance_response(request)
    if value is True:
        value = _need_maintenence_frontend(request)
    if isinstance(value, bool):
        return value
    return True
