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
                    # Low-overhead HMAC signature check using get_signed_cookie
                    raw_val = request.get_signed_cookie(
                        current_cookie_name,
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
                payload = json.dumps({"uid": user.pk, "auth": True})
                response.set_signed_cookie(
                    current_cookie_name,
                    value=payload,
                    salt=self.SIGNING_SALT,
                    max_age=self.cookie_age,
                    httponly=True,
                    secure=not request.META.get("DEVELOPMENT", False),
                    samesite="Lax",
                )
        else:
            # Delete bypass cookie if request is anonymous or logged-out
            if cookie_present:
                response.delete_cookie(current_cookie_name)

        return response
