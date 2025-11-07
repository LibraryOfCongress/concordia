from unittest import mock
from urllib.error import HTTPError

from django.forms import ValidationError
from django.test import TestCase, override_settings

from concordia.turnstile.fields import TurnstileField


class TestFields(TestCase):
    @override_settings(
        TURNSTILE_PROXIES={},
        TURNSTILE_SECRET="test-secret",  # nosec B106: test-only dummy secret
        TURNSTILE_VERIFY_URL="http://example.com",
        TURNSTILE_TIMEOUT=0,
    )
    def test_TurnstileField(self):
        with (
            override_settings(
                TURNSTILE_DEFAULT_CONFIG={"appearance": "interaction-only"}
            ),
            mock.patch("concordia.turnstile.fields.Request"),
            mock.patch("concordia.turnstile.fields.build_opener") as opener_mock,
        ):
            open_mock = opener_mock.return_value.open
            read_mock = open_mock.return_value.read

            field = TurnstileField(required=False)

            self.assertEqual(
                field.widget_attrs(field.widget),
                {"data-appearance": "interaction-only"},
            )

            # Successful validation from Turnstile
            read_mock.return_value = '{"success" : true}'.encode()
            self.assertEqual(field.validate("test-value"), None)

            # Unsuccessful validation from Turnstile
            read_mock.return_value = '{"test-key" : "test-value"}'.encode()
            self.assertRaises(ValidationError, field.validate, "test-value")

            # Error trying to contact Turnstile
            open_mock.side_effect = HTTPError(
                "http://example.com", 404, "Test message%", "", mock.MagicMock()
            )
            self.assertRaises(ValidationError, field.validate, "test-value")

            # Testing special parameters on the widget
            field = TurnstileField(
                onload="testOnload()",
                render="test-render",
                hl="test-hl",
                test_parameter="test-data",
            )
            self.assertEqual(
                field.widget_attrs(field.widget),
                {
                    "data-appearance": "interaction-only",
                    "data-test_parameter": "test-data",
                },
            )
            self.assertEqual(
                field.widget.extra_url,
                {
                    "onload": "testOnload()",
                    "render": "test-render",
                    "hl": "test-hl",
                },
            )
