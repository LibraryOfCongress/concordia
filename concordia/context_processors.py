from django.conf import settings


def system_configuration(request):
    """
    Expose some system configuration to the default template context
    """

    return {
        "SENTRY_PUBLIC_DSN": getattr(settings, "SENTRY_PUBLIC_DSN", None),
        "CONCORDIA_ENVIRONMENT": settings.CONCORDIA_ENVIRONMENT,
    }


def site_navigation(request):
    data = {"VIEW_NAME": request.resolver_match.view_name}

    data["VIEW_NAME_FOR_CSS"] = data["VIEW_NAME"].replace(":", "--")

    path_components = request.path.strip("/").split("/")
    for i, component in enumerate(path_components, start=1):
        data["PATH_LEVEL_%d" % i] = component

    return data
