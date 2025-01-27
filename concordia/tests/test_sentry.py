import importlib
import os
from unittest import mock

from django.test import TestCase

from concordia import celery


class TestSentry(TestCase):
    @mock.patch.dict(
        os.environ,
        {
            "SENTRY_BACKEND_DSN": "http://example.com",
            "CONCORDIA_ENVIRONMENT": "dummy_environment",
        },
    )
    def test_sentry_config(self):
        # Because the celery module is imported during start up,
        # we need to reload it after patching Sentry.
        # release and integrations aren't tested because they
        # are impossible to mock due to the how everything is imported
        # and the functions called are tested elsewhere
        with mock.patch("concordia.celery.sentry_sdk.init") as sentry_mock:
            importlib.reload(celery)
            sentry_mock.assert_called_with(
                "http://example.com",
                environment="dummy_environment",
                release=mock.ANY,
                integrations=mock.ANY,
            )
