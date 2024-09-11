from django.test import TestCase

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
