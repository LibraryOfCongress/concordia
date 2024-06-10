from unittest import mock

import requests
from django.test import TestCase, override_settings

from ..tasks import (
    get_collection_items,
    get_item_id_from_item_url,
    get_item_info_from_result,
    normalize_collection_url,
)


class GetCollectionItemsTests(TestCase):
    @mock.patch.object(requests.Session, "get")
    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.dummy.DummyCache",
            }
        }
    )
    def test_results(self, mock_get):
        class MockResponse:
            def json(self):
                data = {
                    "results": [
                        {
                            "id": 1,
                            "image_url": "https://www.loc.gov/resource/mss85943.000212/",
                            "original_format": {"item"},
                            "url": "https://www.loc.gov/item/mss859430021/",
                        },
                    ],
                    "pagination": {
                        "next": False,
                    },
                }
                return data

        mock_get = mock.Mock()
        mock_get.side_effect = MockResponse()
        items = get_collection_items("https://www.loc.gov/collections/example/")
        self.assertEqual(len(items), 0)

    @mock.patch.object(requests.Session, "get")
    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.dummy.DummyCache",
            }
        }
    )
    def test_ignored_format(self, mock_get):
        class MockResponse:
            def json(self):
                return {
                    "results": [
                        {
                            "id": 1,
                            "original_format": {
                                "collection",
                            },
                            "url": "https://www.loc.gov/item/mss859430021/",
                        },
                    ],
                    "pagination": {},
                }

        mock_get.return_value = MockResponse()
        mock_get.return_value.url = "https://www.loc.gov/collections/example/"
        items = get_collection_items("https://www.loc.gov/collections/example/")
        self.assertEqual(len(items), 0)

    @mock.patch("importer.tasks.requests_retry_session")
    @mock.patch.object(requests.Session, "get")
    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.dummy.DummyCache",
            }
        }
    )
    def no_results(self, mock_get, mock_session):
        class MockResponse:
            def json(self):
                return {
                    "results": [
                        {
                            "id": None,
                            "image_url": None,
                            "original_format": {},
                            "url": "https://www.loc.gov/item/mss859430021/",
                        },
                    ],
                    "pagination": {
                        "next": False,
                    },
                }

        mock_get.return_value = None
        mock_session.get.return_value = MockResponse()
        items = get_collection_items("https://www.loc.gov/collections/example/")
        self.assertEqual(len(items), 0)


class GetItemIdFromItemURLTests(TestCase):
    def test_get_item_id_from_item_url_with_slash(self):
        """
        Testing get item id from item url if ends with /
        """

        url = "https://www.loc.gov/item/mss859430021/"
        resp = get_item_id_from_item_url(url)
        self.assertEqual(resp, "mss859430021")

    def test_get_item_id_from_item_url_without_slash(self):
        """
        Testing get item id from item url if ends without /
        """

        url = "https://www.loc.gov/item/mss859430021"
        resp = get_item_id_from_item_url(url)
        self.assertEqual(resp, "mss859430021")


class GetItemInfoFromResultTests(TestCase):
    def test_no_image_url(self):
        item_info = get_item_info_from_result(
            {
                "id": 1,
                "image_url": False,
                "original_format": {"item"},
            }
        )
        self.assertEqual(item_info, None)

    def test_no_match(self):
        item_info = get_item_info_from_result(
            {
                "id": 1,
                "image_url": "https://www.loc.gov/resource/mss85943.000212/",
                "original_format": {"item"},
                "url": "https://www.loc.com/item/mss859430021/",
            },
        )
        self.assertEqual(item_info, None)

    def test_match(self):
        url = "https://www.loc.gov/item/%s/" % "mss859430021"
        item_info = get_item_info_from_result(
            {
                "id": 1,
                "image_url": "https://www.loc.gov/resource/mss85943.000212/",
                "original_format": {"item"},
                "url": url,
            },
        )
        self.assertEqual(item_info[0], "mss859430021")
        self.assertEqual(item_info[1], url)


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
