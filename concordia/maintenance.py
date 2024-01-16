from django.core.cache import cache
from maintenance_mode.http import (
    need_maintenance_response as base_need_maintenance_response,
)


def _need_maintenence_frontend(request):
    if not hasattr(request, "user"):
        return

    user = request.user

    frontend_available = cache.get("maintenance_mode_frontend_available", False)
    if frontend_available and (user.is_staff or user.is_superuser):
        return False


def need_maintenance_response(request):
    value = base_need_maintenance_response(request)
    print("base")
    print(value)
    if value is True:
        value = _need_maintenence_frontend(request)
        print("frontend")
        print(value)
        if isinstance(value, bool):
            return value
    elif value is False:
        return value
    return True
