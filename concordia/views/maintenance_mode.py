from time import time

from django.core.cache import cache
from django.http import HttpRequest, HttpResponseRedirect
from maintenance_mode.core import set_maintenance_mode


def maintenance_mode_off(request: HttpRequest) -> HttpResponseRedirect:
    """
    Deactivates maintenance mode and redirects to the site root.

    Only superusers are allowed to use this view. If the requesting user is not a
    superuser, no change is made to the system state.

    Returns:
        HttpResponseRedirect: Redirect to the root path with a timestamp parameter
        used for cache busting.
    """
    if request.user.is_superuser:
        set_maintenance_mode(False)

    # Added cache busting to make sure maintenance mode banner is
    # always displayed/removed
    return HttpResponseRedirect("/?t={}".format(int(time())))


def maintenance_mode_on(request: HttpRequest) -> HttpResponseRedirect:
    """
    Activates maintenance mode and redirects to the site root.

    Only superusers are allowed to use this view. If the requesting user is not a
    superuser, no change is made to the system state.

    Returns:
        HttpResponseRedirect: Redirect to the root path with a timestamp parameter
        used for cache busting.
    """
    if request.user.is_superuser:
        set_maintenance_mode(True)

    # Added cache busting to make sure maintenance mode banner is
    # always displayed/removed
    return HttpResponseRedirect("/?t={}".format(int(time())))


def maintenance_mode_frontend_available(request: HttpRequest) -> HttpResponseRedirect:
    """
    Enables frontend access during maintenance mode and redirects to the site root.

    This sets a cache key (`maintenance_mode_frontend_available`) to allow staff and
    superusers to bypass maintenance restrictions while the site is otherwise disabled.
    Only superusers are allowed to use this view.

    Returns:
        HttpResponseRedirect: Redirect to the root path with a timestamp parameter
        used for cache busting.
    """
    if request.user.is_superuser:
        cache.set("maintenance_mode_frontend_available", True, None)

    return HttpResponseRedirect("/?t={}".format(int(time())))


def maintenance_mode_frontend_unavailable(request: HttpRequest) -> HttpResponseRedirect:
    """
    Disables frontend access during maintenance mode and redirects to the site root.

    This clears the `maintenance_mode_frontend_available` cache key, fully locking out
    all users (including staff) from the site frontend during maintenance mode.
    Only superusers are allowed to use this view.

    Returns:
        HttpResponseRedirect: Redirect to the root path with a timestamp parameter
        used for cache busting.
    """
    if request.user.is_superuser:
        cache.set("maintenance_mode_frontend_available", False, None)

    return HttpResponseRedirect("/?t={}".format(int(time())))
