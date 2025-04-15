from time import time

from django.core.cache import cache
from django.http import HttpResponseRedirect
from maintenance_mode.core import set_maintenance_mode


def maintenance_mode_off(request):
    """
    Deactivate maintenance-mode and redirect to site root.
    Only superusers are allowed to use this view.
    """
    if request.user.is_superuser:
        set_maintenance_mode(False)

    # Added cache busting to make sure maintenance mode banner is
    # always displayed/removed
    return HttpResponseRedirect("/?t={}".format(int(time())))


def maintenance_mode_on(request):
    """
    Activate maintenance-mode and redirect to site root.
    Only superusers are allowed to use this view.
    """
    if request.user.is_superuser:
        set_maintenance_mode(True)

    # Added cache busting to make sure maintenance mode banner is
    # always displayed/removed
    return HttpResponseRedirect("/?t={}".format(int(time())))


def maintenance_mode_frontend_available(request):
    """
    Allow staff and superusers to use the front-end
    while maintenance mode is active
    Only superusers are allowed to use this view.
    """
    if request.user.is_superuser:
        cache.set("maintenance_mode_frontend_available", True, None)

    return HttpResponseRedirect("/?t={}".format(int(time())))


def maintenance_mode_frontend_unavailable(request):
    """
    Disallow all use of the front-end while maintenance
    mode is active
    Only superusers are allowed to use this view.
    """
    if request.user.is_superuser:
        cache.set("maintenance_mode_frontend_available", False, None)

    return HttpResponseRedirect("/?t={}".format(int(time())))
