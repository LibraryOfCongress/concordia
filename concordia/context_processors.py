from django.conf import settings


def system_configuration(request):
    """
    Expose some system configuration to the default template context
    """

    return {"SENTRY_PUBLIC_DSN": getattr(settings, "SENTRY_PUBLIC_DSN", None)}
