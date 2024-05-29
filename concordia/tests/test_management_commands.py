from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from concordia.tests.utils import create_asset, create_campaign


class ImportSiteReportsTests(TestCase):
    def test_command_output(self, *args, **kwargs):
        out = StringIO()
        create_campaign(id=1)
        call_command(
            "import_site_reports",
            csv_file="concordia/tests/data/site_reports.csv",
            stdout=out,
        )


class PrintFrontendTestUrlsTests(TestCase):
    def test_command_output(self, *args, **kwargs):
        out = StringIO()
        call_command("print_frontend_test_urls", stdout=out)
        self.assertIn("", out.getvalue())

        create_asset()
        call_command("print_frontend_test_urls", stdout=out)
        self.assertIn("", out.getvalue())
