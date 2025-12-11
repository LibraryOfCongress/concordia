# Originally from
# https://github.com/zmh-program/django-turnstile/blob/main/turnstile/fields.py

import inspect
import json
from logging import getLogger
from typing import Any, Dict
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from concordia.logging import ConcordiaLogger

from ..turnstile.widgets import TurnstileWidget

logger = getLogger(__name__)
structured_logger = ConcordiaLogger.get_logger(__name__)


class TurnstileField(forms.Field):
    """
    Field that renders a Turnstile widget and validates its response token.

    Behavior:
        - Collects widget configuration from keyword arguments that are not
          consumed by `forms.Field.__init__` and stores them in
          `self.widget_settings`.
        - Extracts specific script URL options (`onload`, `render`, `hl`) from
          `self.widget_settings` and assigns them to
          `self.widget.extra_url` for query string construction.
        - Renders using `TurnstileWidget`.
        - Validates the submitted token by POSTing to the configured
          Turnstile verify endpoint and raises `forms.ValidationError` on
          failure.

    Args:
        **kwargs: Standard `forms.Field` keyword arguments plus any Turnstile
            configuration that should be emitted as `data-*` attributes on the
            widget. The following keys are treated as script URL parameters and
            moved to `self.widget.extra_url`:
            - `onload`
            - `render`
            - `hl`

    Attributes:
        widget (TurnstileWidget): The widget class used to render Turnstile.
        default_error_messages (dict[str, str]): Error messages for invalid or
            failed verification states.

    Requirements:
        The following Django settings must be defined:
        - `TURNSTILE_DEFAULT_CONFIG` (dict)
        - `TURNSTILE_JS_API_URL` (string)
        - `TURNSTILE_VERIFY_URL` (string)
        - `TURNSTILE_SECRET` (string)
        - `TURNSTILE_TIMEOUT` (float or int)
        - `TURNSTILE_PROXIES` (dict or None)

    Statuses and errors:
        - Raises `forms.ValidationError(code="error_turnstile")` when an HTTP
          error occurs while contacting the verify endpoint.
        - Raises `forms.ValidationError(code="invalid_turnstile")` when the
          verify endpoint returns a non-success response.
        - Uses the standard `required` message when no token is provided.
    """

    widget = TurnstileWidget
    default_error_messages = {
        "error_turnstile": _("Turnstile could not be verified."),
        "invalid_turnstile": _("Turnstile could not be verified."),
        "required": _("Please prove you are a human."),
    }

    def __init__(self, **kwargs: Any) -> None:
        """
        Initialize the field and partition keyword arguments.

        Behavior:
            - Splits `kwargs` into those accepted by `forms.Field.__init__`
              and those intended as Turnstile configuration.
            - Moves `onload`, `render`, and `hl` from the configuration into
              `self.widget.extra_url` so they are appended to the API script
              URL as a query string.
            - Retains the remaining configuration in `self.widget_settings` to
              be emitted as `data-*` attributes by `widget_attrs`.
        """
        superclass_parameters = inspect.signature(super().__init__).parameters
        superclass_kwargs: Dict[str, Any] = {}
        widget_settings = settings.TURNSTILE_DEFAULT_CONFIG.copy()
        for key, value in kwargs.items():
            if key in superclass_parameters:
                superclass_kwargs[key] = value
            else:
                widget_settings[key] = value

        widget_url_settings: Dict[str, Any] = {}
        for prop in filter(lambda p: p in widget_settings, ("onload", "render", "hl")):
            widget_url_settings[prop] = widget_settings[prop]
            del widget_settings[prop]
        self.widget_settings = widget_settings

        super().__init__(**superclass_kwargs)

        self.widget.extra_url = widget_url_settings

    def widget_attrs(self, widget: forms.Widget) -> dict[str, Any]:
        """
        Extend `forms.Field.widget_attrs`.

        Behavior:
            Calls the base implementation to get default attributes, then adds
            one `data-*` attribute per key in `self.widget_settings`. Keys are
            lowercased as-is and prefixed with `data-`.

        Returns:
            dict[str, Any]: Combined widget attributes.
        """
        attrs = super().widget_attrs(widget)
        for key, value in self.widget_settings.items():
            attrs["data-%s" % key] = value
        return attrs

    def validate(self, value: str | None) -> None:
        """
        Validate the submitted Turnstile token against the verify endpoint.

        Behavior:
            - Calls `forms.Field.validate` for base required checks.
            - Issues a POST request to `settings.TURNSTILE_VERIFY_URL` using
              `urllib` with `TURNSTILE_PROXIES` and `TURNSTILE_TIMEOUT`.
            - Parses the JSON response and checks the `success` field.

        Args:
            value (str | None): The token returned by the Turnstile widget.

        Raises:
            forms.ValidationError: If Turnstile verification fails or if an HTTP
                error occurs while contacting the verify endpoint.
        """
        super().validate(value)

        structured_logger.debug(
            "Turnstile validation started.",
            event_code="turnstile_validate_start",
            has_token=bool(value),
            verify_url=settings.TURNSTILE_VERIFY_URL,
        )

        opener = build_opener(ProxyHandler(settings.TURNSTILE_PROXIES))
        post_data = urlencode(
            {
                "secret": settings.TURNSTILE_SECRET,
                "response": value,
            }
        ).encode()

        request = Request(settings.TURNSTILE_VERIFY_URL, post_data)

        try:
            structured_logger.debug(
                "Submitting token to Turnstile verify endpoint.",
                event_code="turnstile_request_submit",
                verify_url=settings.TURNSTILE_VERIFY_URL,
            )
            response = opener.open(request, timeout=settings.TURNSTILE_TIMEOUT)
            structured_logger.debug(
                "Received response from Turnstile verify endpoint.",
                event_code="turnstile_response_received",
                verify_url=settings.TURNSTILE_VERIFY_URL,
                http_status=getattr(response, "status", None),
            )
        except HTTPError as exc:
            logger.exception("HTTPError received from Turnstile: %s", exc, exc_info=exc)
            structured_logger.exception(
                "HTTPError received from Turnstile verify endpoint.",
                event_code="turnstile_http_error",
                reason="HTTP error while contacting Turnstile verify endpoint",
                reason_code="http_error",
                verify_url=settings.TURNSTILE_VERIFY_URL,
                http_status=getattr(exc, "code", None),
            )
            raise forms.ValidationError(
                self.error_messages["error_turnstile"], code="error_turnstile"
            ) from exc

        response_data = json.loads(response.read().decode("utf-8"))

        # Non-success responses from Turnstile.
        if not response_data.get("success"):
            logger.exception(
                "Failure received from Turnstile. Error codes: %s. Messages: %s",
                response_data.get("error-codes"),
                response_data.get("messages"),
            )
            structured_logger.info(
                "Turnstile verification failed.",
                event_code="turnstile_validate_failed",
                verify_url=settings.TURNSTILE_VERIFY_URL,
                error_codes=response_data.get("error-codes"),
                messages=response_data.get("messages"),
            )
            raise forms.ValidationError(
                self.error_messages["invalid_turnstile"], code="invalid_turnstile"
            )

        structured_logger.debug(
            "Turnstile verification succeeded.",
            event_code="turnstile_validate_success",
            verify_url=settings.TURNSTILE_VERIFY_URL,
        )
