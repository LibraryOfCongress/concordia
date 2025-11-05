import sys
from unittest import mock

import requests
from django.core.cache.backends.base import BaseCache
from django.test import TestCase, override_settings

from concordia.tests.utils import CreateTestUsers
from importer import tasks
from importer.tasks.collections import (
    import_collection_task,
    normalize_collection_url,
)
from importer.tests.utils import create_import_job


class MockResponse:
    def __init__(self, original_format="item"):
        self.original_format = original_format

    def json(self):
        url = "https://www.loc.gov/item/%s/" % "mss859430021"
        return {
            "results": [
                {
                    "id": 1,
                    "image_url": "https://www.loc.gov/resource/mss85943.000212/",
                    "original_format": {self.original_format},
                    "url": url,
                },
            ],
            "pagination": {},
        }


class MockCache(BaseCache):
    def __init__(self, host, *args, **kwargs):
        params = {}
        super().__init__(params, **kwargs)

    def get(self, key, default=None, version=None):
        resp = MockResponse()
        return resp


# Ensure dotted path used in override_settings still resolves after splitting.
# The original tests referenced "importer.tests.test_tasks.MockCache".
# Point that module name at this module so the cache backend can import it.
sys.modules.setdefault("importer.tests.test_tasks", sys.modules[__name__])


class GetCollectionItemsTests(TestCase):
    @mock.patch.object(requests.Session, "get")
    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.dummy.DummyCache",
            }
        }
    )
    def test_cache_miss(self, mock_get):
        mock_get.return_value = MockResponse()
        mock_get.return_value.url = "https://www.loc.gov/collections/example/"
        items = tasks.collections.get_collection_items(
            "https://www.loc.gov/collections/example/"
        )
        self.assertEqual(len(items), 1)

    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "importer.tests.test_tasks.MockCache",
            }
        }
    )
    def test_cache_hit(self):
        items = tasks.collections.get_collection_items(
            "https://www.loc.gov/collections/example/"
        )
        self.assertEqual(len(items), 1)

    @mock.patch.object(requests.Session, "get")
    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.dummy.DummyCache",
            }
        }
    )
    def test_ignored_format(self, mock_get):
        mock_get.return_value = MockResponse(original_format="collection")
        mock_get.return_value.url = "https://www.loc.gov/collections/example/"
        with self.assertLogs("importer.tasks", level="INFO") as log:
            items = tasks.collections.get_collection_items(
                "https://www.loc.gov/collections/example/"
            )

            self.assertEqual(
                log.output[0],
                "INFO:importer.tasks.items:"
                "Skipping result 1 because it contains an "
                "unsupported format: {'collection'}",
            )
        self.assertEqual(len(items), 0)

    def test_multiple_items(self):
        with (
            mock.patch("importer.tasks.collections.cache") as cache_mock,
            mock.patch(
                "importer.tasks.collections.requests_retry_session"
            ) as requests_mock,
            mock.patch(
                "importer.tasks.collections.get_item_info_from_result"
            ) as result_mock,
        ):
            cache_mock.get.return_value = None
            requests_mock.return_value.get.return_value.json.return_value = {
                "results": [1, 2, 3]
            }
            # Each time this mock is called, the next value in the list
            # is returned
            result_mock.side_effect = [4, 5, None]

            items = tasks.collections.get_collection_items("http://example.com")

            self.assertEqual(items, [4, 5])
            self.assertEqual(result_mock.call_count, 3)

    def test_no_results(self):
        with (
            mock.patch("importer.tasks.collections.cache") as cache_mock,
            mock.patch(
                "importer.tasks.collections.requests_retry_session"
            ) as requests_mock,
            self.assertLogs("importer.tasks", level="ERROR") as log,
        ):
            cache_mock.get.return_value = None
            requests_mock.return_value.get.return_value.json.return_value = {}
            items = tasks.collections.get_collection_items("http://example.com")
            self.assertEqual(items, [])
            self.assertEqual(
                log.output,
                [
                    "ERROR:importer.tasks.collections:"
                    'Expected URL http://example.com to include "results"'
                ],
            )

    def test_get_info_exception(self):
        with (
            mock.patch("importer.tasks.collections.cache") as cache_mock,
            mock.patch(
                "importer.tasks.collections.requests_retry_session"
            ) as requests_mock,
            mock.patch("importer.tasks.items.get_item_info_from_result") as result_mock,
            self.assertLogs("importer.tasks", level="WARNING") as log,
        ):
            cache_mock.get.return_value = None
            requests_mock.return_value.get.return_value.json.return_value = {
                "results": [1]
            }
            result_mock.side_effect = AttributeError

            items = tasks.collections.get_collection_items("http://example.com")

            self.assertEqual(items, [])
            # The first log entry contains a stack trace, so we use assertIn
            # rather than assertEqual here
            self.assertIn(
                "WARNING:importer.tasks.collections:"
                "Skipping result from http://example.com which did not match "
                "expected format:",
                log.output[0],
            )
            self.assertEqual(
                log.output[1],
                "WARNING:importer.tasks.collections:"
                "No valid items found for collection url: http://example.com",
            )


class ImportCollectionTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.login_user()

    @mock.patch("importer.tasks.collections.get_collection_items")
    @mock.patch("importer.tasks.collections.normalize_collection_url")
    def test_import_collection(self, mock_get, mock_normalize):
        magic_mock = mock.MagicMock()
        magic_mock.request = mock.MagicMock()
        magic_mock.request.id = 1
        import_job = create_import_job(created_by=self.user)
        mock_get.return_value = ((None, None),)
        import_collection_task(import_job.pk)
        self.assertTrue(mock_get.called)


class CollectionURLNormalizationTests(TestCase):
    def test_basic_normalization(self):
        self.assertEqual(
            normalize_collection_url(
                "https://www.loc.gov/collections/branch-rickey-papers/"
            ),
            "https://www.loc.gov/collections/branch-rickey-papers/?fo=json",
        )

    def test_extra_querystring_parameters(self):
        self.assertEqual(
            normalize_collection_url(
                "https://www.loc.gov/collections/branch-rickey-papers/?foo=bar"
            ),
            "https://www.loc.gov/collections/branch-rickey-papers/?fo=json&foo=bar",
        )

    def test_conflicting_querystring_parameters(self):
        self.assertEqual(
            normalize_collection_url(
                "https://www.loc.gov/collections/branch-rickey-papers/?foo=bar&fo=xml&sp=99&at=item"  # NOQA
            ),
            "https://www.loc.gov/collections/branch-rickey-papers/?fo=json&foo=bar",
        )
