from maintenance_mode.http import get_maintenance_response
from maintenance_mode.middleware import (
    MaintenanceModeMiddleware as BaseMaintenanceModeMiddleware,
)

from .maintenance import need_maintenance_response


class MaintenanceModeMiddleware(BaseMaintenanceModeMiddleware):
    def process_request(self, request):
        if need_maintenance_response(request):
            return get_maintenance_response(request)
        return None
