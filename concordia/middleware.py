import json

from django.conf import settings
from django.core import signing
from django.utils.deprecation import MiddlewareMixin
from maintenance_mode.http import get_maintenance_response
from maintenance_mode.middleware import (
    MaintenanceModeMiddleware as BaseMaintenanceModeMiddleware,
)

from concordia.logging import ConcordiaLogger

from .maintenance import need_maintenance_response

structured_logger = ConcordiaLogger.get_logger(__name__)


class MaintenanceModeMiddleware(BaseMaintenanceModeMiddleware):
    def process_request(self, request):
        if need_maintenance_response(request):
            return get_maintenance_response(request)
        return None


class CloudflareAuthStatusMiddleware(MiddlewareMixin):
    """
    Manage HMAC-signed cookies for authenticated users.

    Validates and sets an HMAC-signed cookie on HTTP responses for authenticated,
    non-anonymous users. Allows Cloudflare Edge WAF rules to bypass challenges
    for verified users while checking signatures in Django before database access.
    """

    SIGNING_SALT = "concordia.cloudflare.auth_status"

    @property
    def cookie_name(self):
        """
        Return the configured Cloudflare authentication cookie name.

        :return: Dynamic or default cookie name.
        :rtype: str
        """
        return getattr(settings, "CLOUDFLARE_AUTH_STATUS_COOKIE_NAME", "_cf_acc_status")

    @property
    def cookie_age(self):
        """Return the maximum age in seconds for the authentication cookie.

        :return: Cookie max age in seconds.
        :rtype: int
        """
        return getattr(settings, "CLOUDFLARE_AUTH_STATUS_COOKIE_AGE", 86400 * 7)

    def process_response(self, request, response):
        """Verify request signature and attach or clear the edge bypass cookie.

        If the user is authenticated, inspects the incoming signed cookie.
        Re-issues a signed cookie if missing or invalid, or deletes the cookie
        if the request is unauthenticated or logged out.

        :param request: Incoming HTTP request object.
        :type request: django.http.HttpRequest
        :param response: Outgoing HTTP response object.
        :type response: django.http.HttpResponse
        :return: Modified HTTP response object with updated cookie headers.
        :rtype: django.http.HttpResponse
        """
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
                    # Low-overhead HMAC signature check using get_signed_cookie
                    raw_val = request.get_signed_cookie(
                        current_cookie_name,
                        default=None,
                        salt=self.SIGNING_SALT,
                        max_age=self.cookie_age,
                    )
                    if raw_val is not None:
                        data = json.loads(raw_val)
                        if isinstance(data, dict) and data.get("uid") == user.pk:
                            valid_signature = True
                        else:
                            structured_logger.warning(
                                "Cloudflare auth cookie payload is corrupt or"
                                " invalid JSON.",
                                event_code="cloudflare_auth_cookie_corrupt_payload",
                                reason="Payload is not a valid dict or missing"
                                " user ID.",
                                reason_code="invalid_payload_structure",
                                user=user,
                            )
                except signing.BadSignature:
                    structured_logger.warning(
                        "Cloudflare auth cookie failed signature validation.",
                        event_code="cloudflare_auth_cookie_bad_signature",
                        reason="HMAC signature did not match.",
                        reason_code="signature_mismatch",
                        user=user,
                    )
                    valid_signature = False
                except (ValueError, json.JSONDecodeError):
                    structured_logger.warning(
                        "Cloudflare auth cookie payload is corrupt or invalid JSON.",
                        event_code="cloudflare_auth_cookie_corrupt_payload",
                        reason="Failed to parse cookie payload.",
                        reason_code="invalid_json",
                        user=user,
                    )
                    valid_signature = False

            # Re-issue or set fresh signed cookie if invalid, missing, or expired
            if not valid_signature:
                payload = json.dumps({"uid": user.pk})
                response.set_signed_cookie(
                    current_cookie_name,
                    value=payload,
                    salt=self.SIGNING_SALT,
                    max_age=self.cookie_age,
                    httponly=True,
                    secure=not request.META.get("DEVELOPMENT", False),
                    samesite="Lax",
                )
        elif cookie_present:
            # Delete bypass cookie if request is anonymous or logged-out
            response.delete_cookie(current_cookie_name)

        return response
