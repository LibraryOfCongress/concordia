from django.conf import settings
from django.core.cache import cache


def system_configuration(request):
    """
    Expose some system configuration to the default template context
    """

    return {
        "SENTRY_FRONTEND_DSN": getattr(settings, "SENTRY_FRONTEND_DSN", None),
        "CONCORDIA_ENVIRONMENT": settings.CONCORDIA_ENVIRONMENT,
        "S3_BUCKET_NAME": getattr(settings, "S3_BUCKET_NAME", None),
        "APPLICATION_VERSION": getattr(settings, "APPLICATION_VERSION", None),
    }


def site_navigation(request):
    data = {}

    if request.resolver_match:
        data["VIEW_NAME"] = request.resolver_match.view_name
        data["VIEW_NAME_FOR_CSS"] = data["VIEW_NAME"].replace(":", "--")

    path_components = request.path.strip("/").split("/")
    for i, component in enumerate(path_components, start=1):
        data["PATH_LEVEL_%d" % i] = component

    return data


def maintenance_mode_frontend_available(request):
    value = cache.get("maintenance_mode_frontend_available", False)
    return {"maintenance_mode_frontend_available": value}


def turnstile_default_settings(request):
    """
    Expose turnstile default settings to the default template context
    - Cloudflare Turnstile
    """

    return {
        "TURN_JS_API_URL": getattr(
            settings,
            "TURNSTILE_JS_API_URL",
            "https://challenges.cloudflare.com/turnstile/v0/api.js",
        ),
        "TURN_VERIFY_URL": getattr(
            settings,
            "TURNSTILE_VERIFY_URL",
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        ),
        "TURN_SITEKEY": getattr(
            settings, "TURNSTILE_SITEKEY", "1x00000000000000000000AA"
        ),
        "TURN_SECRET": getattr(
            settings, "TURNSTILE_SECRET", "1x0000000000000000000000000000000AA"
        ),
        "TURN_TIMEOUT": getattr(settings, "TURNSTILE_TIMEOUT", 5),
        "TURN_DEFAULT_CONFIG": getattr(settings, "TURNSTILE_DEFAULT_CONFIG", {}),
        "TURN_PROXIES": getattr(settings, "TURNSTILE_PROXIES", {}),
    }
