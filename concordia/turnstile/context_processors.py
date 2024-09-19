from django.conf import settings


def turnstile_default_settings(request):
    """
    Expose turnstile default settings to the default template context
    - Cloudflare Turnstile
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
            settings, "TURNSTILE_SECRET", "1x0000000000000000000000000000000AA"
        ),
        "TURNSTILE_TIMEOUT": getattr(settings, "TURNSTILE_TIMEOUT", 5),
        "TURNSTILE_DEFAULT_CONFIG": getattr(settings, "TURNSTILE_DEFAULT_CONFIG", {}),
        "TURNSTILE_PROXIES": getattr(settings, "TURNSTILE_PROXIES", {}),
    }
