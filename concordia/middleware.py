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
    Sets an HMAC-signed cookie (_cf_acc_status) for authenticated, non-anonymous users.
    Cloudflare Edge WAF rules evaluate this cookie to bypass challenges for logged-in
    users.
    """

    COOKIE_NAME = "_cf_acc_status"
    SIGNING_SALT = "concordia.cloudflare.auth_status"

    def process_response(self, request, response):
        user = getattr(request, "user", None)
        is_authenticated = bool(
            user and user.is_authenticated and not user.is_anonymous
        )
        cookie_present = self.COOKIE_NAME in request.COOKIES

        if is_authenticated:
            # Issue or keep signed cookie active
            expected_token = signing.dumps(
                {"uid": user.pk, "auth": True}, salt=self.SIGNING_SALT
            )

            # Verify current cookie validity to avoid re-setting on every request
            # unless needed
            needs_cookie = True
            if cookie_present:
                try:
                    data = signing.loads(
                        request.COOKIES[self.COOKIE_NAME],
                        salt=self.SIGNING_SALT,
                        max_age=86400 * 7,
                    )
                    if data.get("uid") == user.pk and data.get("auth") is True:
                        needs_cookie = False
                except (signing.BadSignature, signing.SignatureExpired):
                    needs_cookie = True

            if needs_cookie:
                response.set_cookie(
                    self.COOKIE_NAME,
                    expected_token,
                    max_age=86400 * 7,  # 7 days
                    httponly=True,
                    secure=not request.META.get("DEVELOPMENT", False),
                    samesite="Lax",
                )
        else:
            # Delete cookie if anonymous or logged out
            if cookie_present:
                response.delete_cookie(self.COOKIE_NAME)

        return response
