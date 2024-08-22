from django.conf import settings


def turnstile_settings(request):
    return {"TURN_JS_API_URL": settings.TURN_JS_API_URL}
