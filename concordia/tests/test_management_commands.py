from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from concordia.tests.utils import create_asset, create_campaign


class EnsureInitialSiteConfigurationTests(TestCase):
    def test_command_output(self, *args, **kwargs):
        out = StringIO()
        call_command(
            "ensure_initial_site_configuration", admin_email="admin@loc.gov", stdout=out
        )
        call_command(
            "ensure_initial_site_configuration", site_domain="crowd.loc.gov", stdout=out
        )
        with mock.patch(
            "django.contrib.sites.models.Site.objects.update"
        ) as update_mock:
            update_mock.return_value = 0
            call_command(
                "ensure_initial_site_configuration",
                site_domain="crowd.loc.gov",
                stdout=out,
            )


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
