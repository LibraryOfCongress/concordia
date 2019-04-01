from django.conf import settings
from flags.state import flag_enabled

from concordia.version import get_concordia_version


def system_configuration(request):
    """
    Expose some system configuration to the default template context
    """

    return {
        "SENTRY_FRONTEND_DSN": getattr(settings, "SENTRY_FRONTEND_DSN", None),
        "CONCORDIA_ENVIRONMENT": settings.CONCORDIA_ENVIRONMENT,
        "S3_BUCKET_NAME": getattr(settings, "S3_BUCKET_NAME", None),
        "APPLICATION_VERSION": get_concordia_version(),
        "RAVEN_CONFIG": settings.RAVEN_CONFIG,
        "ACTIVITY_UI_ENABLED": flag_enabled("ACTIVITY_UI", request=request),
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
