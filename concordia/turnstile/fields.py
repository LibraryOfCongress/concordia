# Originally from
# https://github.com/zmh-program/django-turnstile/blob/main/turnstile/fields.py

import inspect
import json
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from ..turnstile.widgets import TurnstileWidget


class TurnstileField(forms.Field):
    widget = TurnstileWidget
    default_error_messages = {
        "error_turnstile": _("Turnstile could not be verified."),
        "invalid_turnstile": _("Turnstile could not be verified."),
        "required": _("Please prove you are a human."),
    }

    def __init__(self, **kwargs):
        superclass_parameters = inspect.signature(super().__init__).parameters
        superclass_kwargs = {}
        widget_settings = settings.TURNSTILE_DEFAULT_CONFIG.copy()
        for key, value in kwargs.items():
            if key in superclass_parameters:
                superclass_kwargs[key] = value
            else:
                widget_settings[key] = value

        widget_url_settings = {}
        for prop in filter(lambda p: p in widget_settings, ("onload", "render", "hl")):
            widget_url_settings[prop] = widget_settings[prop]
            del widget_settings[prop]
        self.widget_settings = widget_settings

        super().__init__(**superclass_kwargs)

        self.widget.extra_url = widget_url_settings

    def widget_attrs(self, widget):
        attrs = super().widget_attrs(widget)
        for key, value in self.widget_settings.items():
            attrs["data-%s" % key] = value
        return attrs

    def validate(self, value):
        super().validate(value)

        opener = build_opener(ProxyHandler(settings.TURNSTILE_PROXIES))
        post_data = urlencode(
            {
                "secret": settings.TURNSTILE_SECRET,
                "response": value,
            }
        ).encode()

        request = Request(settings.TURNSTILE_VERIFY_URL, post_data)

        try:
            response = opener.open(request, timeout=settings.TURNSTILE_TIMEOUT)
        except HTTPError as exc:
            raise forms.ValidationError(
                self.error_messages["error_turnstile"], code="error_turnstile"
            ) from exc

        response_data = json.loads(response.read().decode("utf-8"))

        if not response_data.get("success"):
            raise forms.ValidationError(
                self.error_messages["invalid_turnstile"], code="invalid_turnstile"
            )
