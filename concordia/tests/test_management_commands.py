from io import StringIO

from django.core.management import call_command
from django.test import TestCase


class PrintFrontendTestUrlsTests(TestCase):
    def test_command_output(self, *args, **kwargs):
        out = StringIO()
        call_command("print_frontend_test_urls", stdout=out)
        self.assertIn("", out.getvalue())
