from typing import Any, Dict

from django.conf import settings
from django.http import HttpRequest


def turnstile_default_settings(request: "HttpRequest") -> "Dict[str, Any]":
    """
    Provide Turnstile-related settings to template context.

    Behavior:
        Mirrors a subset of Django settings into a dictionary for use in
        templates. Values are retrieved with `getattr` so that each key has a
        sensible default even if the corresponding setting is not defined.

    Args:
        request (HttpRequest): The current request. Included to satisfy the
            Django context processor signature; it is not used.

    Returns:
        Dict[str, Any]: Mapping of keys to values for template context. Keys:
            - "TURNSTILE_JS_API_URL" (str): Base URL for the Turnstile
              JavaScript API. Default:
              "https://challenges.cloudflare.com/turnstile/v0/api.js".
            - "TURNSTILE_VERIFY_URL" (str): Verification endpoint used by the
              server to validate tokens. Default:
              "https://challenges.cloudflare.com/turnstile/v0/siteverify".
            - "TURNSTILE_SITEKEY" (str): Public site key. Default:
              "1x00000000000000000000BB".
            - "TURNSTILE_SECRET" (str): Private secret key. Default:
              "1x0000000000000000000000000000000AA".
            - "TURNSTILE_TIMEOUT" (int): Timeout in seconds for verification
              requests. Default: 5.
            - "TURNSTILE_DEFAULT_CONFIG" (dict[str, Any]): Default widget
              configuration applied as `data-*` attributes. Default: {}.
            - "TURNSTILE_PROXIES" (dict[str, Any]): Proxy configuration for
              outbound verification requests. Default: {}.
    """
    return {
        "TURNSTILE_JS_API_URL": getattr(
            settings,
            "TURN_JS_API_URL",
            "https://challenges.cloudflare.com/turnstile/v0/api.js",
        ),
        "TURNSTILE_VERIFY_URL": getattr(
            settings,
            "TURNSTILE_VERIFY_URL",
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        ),
        "TURNSTILE_SITEKEY": getattr(
            settings, "TURNSTILE_SITEKEY", "1x00000000000000000000BB"
        ),
        "TURNSTILE_SECRET": getattr(
            settings,
            "TURNSTILE_SECRET",
            "1x0000000000000000000000000000000AA",  # nosec B106: test-only dummy secret
        ),
        "TURNSTILE_TIMEOUT": getattr(settings, "TURNSTILE_TIMEOUT", 5),
        "TURNSTILE_DEFAULT_CONFIG": getattr(settings, "TURNSTILE_DEFAULT_CONFIG", {}),
        "TURNSTILE_PROXIES": getattr(settings, "TURNSTILE_PROXIES", {}),
    }
