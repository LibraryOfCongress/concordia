# Originally from
# https://github.com/zmh-program/django-turnstile/blob/main/turnstile/widgets.py

from typing import Any, Dict, Mapping
from urllib.parse import urlencode

from django import forms
from django.conf import settings


class TurnstileWidget(forms.Widget):
    """
    A Django form widget for Cloudflare Turnstile.

    Behavior:
        Renders using the `forms/widgets/turnstile_widget.html` template and
        augments the base widget behavior by injecting the configured site key
        into the rendered attributes and the Turnstile script URL into the
        template context. Optional query parameters for the script URL may be
        supplied via the `extra_url` dictionary.

    Requirements:
        - `settings.TURNSTILE_SITEKEY` must be defined.
        - `settings.TURNSTILE_JS_API_URL` must be defined.

    Attributes:
        template_name (str): Template used to render the widget.
        extra_url (Dict[str, str]): Optional query parameters appended to the
            Turnstile JavaScript URL.
    """

    template_name = "forms/widgets/turnstile_widget.html"

    def __init__(self, *args, **kwargs) -> None:
        """
        Initialize the widget.

        Notes:
            Initializes `extra_url` to an empty dictionary.

        Args:
            *args (Any): Positional arguments passed through to `forms.Widget`.
            **kwargs (Any): Keyword arguments passed through to `forms.Widget`.
        """
        self.extra_url = {}
        super().__init__(*args, **kwargs)

    def value_from_datadict(
        self,
        data: "Mapping[str, Any]",
        files: "Mapping[str, Any]",
        name: str,
    ) -> "str | None":
        """
        Extract the Turnstile response token from submitted form data.

        Request Parameters:
            - `cf-turnstile-response` (str): The token provided by the
              Turnstile widget.

        Args:
            data (Mapping[str, Any]): The POST data.
            files (Mapping[str, Any]): The file data (unused).
            name (str): The field name (unused for extraction).

        Returns:
            str | None: The Turnstile token if present, otherwise `None`.
        """
        return data.get("cf-turnstile-response")

    def build_attrs(
        self,
        base_attrs: "Dict[str, Any]",
        extra_attrs: "Dict[str, Any] | None" = None,
    ) -> "Dict[str, Any]":
        """
        Override of `forms.Widget.build_attrs`.

        Difference from base:
            Calls the base method to merge attributes, then sets the
            `data-sitekey` attribute using `settings.TURNSTILE_SITEKEY`.

        Args:
            base_attrs (Dict[str, Any]): Base HTML attributes.
            extra_attrs (Dict[str, Any] | None): Additional attributes to merge.

        Returns:
            Dict[str, Any]: The merged attributes with `data-sitekey` set.
        """
        attrs = super().build_attrs(base_attrs, extra_attrs)
        attrs["data-sitekey"] = settings.TURNSTILE_SITEKEY
        return attrs

    def get_context(
        self,
        name: str,
        value: "Any",
        attrs: "Dict[str, Any] | None",
    ) -> "Dict[str, Any]":
        """
        Override of `forms.Widget.get_context`.

        Difference from base:
            Calls the base method to build the context, then adds `api_url`
            from `settings.TURNSTILE_JS_API_URL`. If `extra_url` has entries,
            appends them as a query string.

        Args:
            name (str): Field name.
            value (Any): Field value.
            attrs (Dict[str, Any] | None): HTML attributes for rendering.

        Returns:
            Dict[str, Any]: Template context including `api_url`.
        """
        context = super().get_context(name, value, attrs)
        context["api_url"] = settings.TURNSTILE_JS_API_URL
        if self.extra_url:
            context["api_url"] += "?" + urlencode(self.extra_url)
        return context
