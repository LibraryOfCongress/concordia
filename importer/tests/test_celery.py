from unittest import mock

from django.test import TestCase

from importer.celery import configure_logging


class ConfigureLoggingTests(TestCase):
    @mock.patch("logging.config.dictConfig")
    @mock.patch("django.conf.settings", new={})
    def test_configure_logging_applies_settings(self, mock_dict_config):
        """
        Test that configure_logging correctly applies Django's logging settings.
        """
        with mock.patch("django.conf.settings") as mock_settings:
            mock_settings.LOGGING = {"version": 1}
            configure_logging()
            mock_dict_config.assert_called_once_with({"version": 1})
