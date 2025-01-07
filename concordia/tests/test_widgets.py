from django.test import TestCase, override_settings

from concordia.turnstile.widgets import TurnstileWidget
from concordia.widgets import EmailWidget


class TestWidgets(TestCase):
    def test_EmailWidget(self):
        widget = EmailWidget()
        output = widget.render("email", None)
        self.assertHTMLEqual(
            output, '<input class="fst-italic form-control" name="email" type="email">'
        )

        output = widget.render("email", "test@example.com")
        self.assertHTMLEqual(
            output,
            '<input class="fst-italic form-control" name="email"'
            ' placeholder="Change your email address" type="email">',
        )

        output = widget.render("email", None, attrs={"display": "none;"})
        self.assertHTMLEqual(
            output,
            '<input class="fst-italic form-control" display="none;"'
            ' name="email" type="email">',
        )

    @override_settings(TURNSTILE_SITEKEY="test-key", TURNSTILE_JS_API_URL="test-url")
    def test_TurnstileWidget(self):
        widget = TurnstileWidget()

        # Testing basic validation
        self.assertEqual(widget.value_from_datadict({}, None, None), None)

        # Testing validation with data
        data = {"cf-turnstile-response": "test-data"}
        self.assertEqual(widget.value_from_datadict(data, None, None), "test-data")

        # Testing basic attrs
        self.assertEqual(widget.build_attrs({}), {"data-sitekey": "test-key"})

        # Testing with extra ttrs
        self.assertEqual(
            widget.build_attrs(
                {"id": "test-id"}, extra_attrs={"custom-attr": "test-attr"}
            ),
            {"data-sitekey": "test-key", "id": "test-id", "custom-attr": "test-attr"},
        )

        # Testing basic context
        self.assertEqual(
            widget.get_context("test-name", "test value", {}),
            {
                "widget": {
                    "name": "test-name",
                    "is_hidden": False,
                    "required": False,
                    "value": "test value",
                    "attrs": {"data-sitekey": "test-key"},
                    "template_name": "forms/widgets/turnstile_widget.html",
                },
                "api_url": "test-url",
            },
        )

        # Testing with special context
        widget.extra_url = {
            "test-parameter1": "test-value1",
            "test-parameter2": "test-value2",
        }
        self.assertEqual(
            widget.get_context("test-name", "test value", {}),
            {
                "widget": {
                    "name": "test-name",
                    "is_hidden": False,
                    "required": False,
                    "value": "test value",
                    "attrs": {"data-sitekey": "test-key"},
                    "template_name": "forms/widgets/turnstile_widget.html",
                },
                "api_url": "test-url?test-parameter1=test-value1&"
                "test-parameter2=test-value2",
            },
        )
