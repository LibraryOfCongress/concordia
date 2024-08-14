# Originally from
# https://github.com/AndrejZbin/django-hcaptcha/blob/master/hcaptcha/widgets.py

from urllib.parse import urlencode

from django import forms

from ..settings_template import TURN_JS_API_URL, TURN_SITEKEY


class TurnstileWidget(forms.Widget):
    template_name = "forms/widgets/turnstile_widget.html"

    def __init__(self, *args, **kwargs):
        self.extra_url = {}
        super().__init__(*args, **kwargs)

    def value_from_datadict(self, data, files, name):
        return data.get("cf-turnstile-response")

    def build_attrs(self, base_attrs, extra_attrs=None):
        attrs = super().build_attrs(base_attrs, extra_attrs)
        attrs["data-sitekey"] = TURN_SITEKEY
        return attrs

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["api_url"] = TURN_JS_API_URL
        if self.extra_url:
            context["api_url"] += "?" + urlencode(self.extra_url)
        return context
