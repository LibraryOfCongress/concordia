from django.conf import settings
from django.core import signing
from django.utils.deprecation import MiddlewareMixin
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


class CloudflareAuthStatusMiddleware(MiddlewareMixin):
    """
    Sets and validates an HMAC-signed cookie for authenticated, non-anonymous users.
    Allows Cloudflare Edge rules to bypass challenges for logged-in users while
    validating HMAC signatures early in Django before expensive DB operations occur.
    """

    SIGNING_SALT = "concordia.cloudflare.auth_status"

    @property
    def cookie_name(self):
        return getattr(settings, "CLOUDFLARE_AUTH_STATUS_COOKIE_NAME", "_cf_acc_status")

    @property
    def cookie_age(self):
        return getattr(settings, "CLOUDFLARE_AUTH_STATUS_COOKIE_AGE", 86400 * 7)

    def process_response(self, request, response):
        user = getattr(request, "user", None)
        is_authenticated = bool(
            user and user.is_authenticated and not user.is_anonymous
        )
        current_cookie_name = self.cookie_name
        cookie_present = current_cookie_name in request.COOKIES

        if is_authenticated:
            valid_signature = False

            if cookie_present:
                try:
                    # Low-overhead HMAC signature check using signing.loads
                    cookie_val = request.COOKIES[current_cookie_name]
                    data = signing.loads(
                        cookie_val,
                        salt=self.SIGNING_SALT,
                        max_age=self.cookie_age,
                    )
                    if isinstance(data, dict) and data.get("uid") == user.pk:
                        valid_signature = True
                except (signing.BadSignature, signing.SignatureExpired, ValueError):
                    valid_signature = False

            # Set/refresh the signed cookie if missing, expired, or tampered
            if not valid_signature:
                signed_val = signing.dumps(
                    {"uid": user.pk, "auth": True}, salt=self.SIGNING_SALT
                )
                response.set_cookie(
                    current_cookie_name,
                    value=signed_val,
                    max_age=self.cookie_age,
                    httponly=True,
                    secure=not request.META.get("DEVELOPMENT", False),
                    samesite="Lax",
                )
        else:
            # Delete cookie if request is anonymous or logged-out
            if cookie_present:
                response.delete_cookie(current_cookie_name)

        return response
