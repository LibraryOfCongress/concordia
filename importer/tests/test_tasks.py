import concurrent.futures
from unittest import mock

import requests
from django.core.cache.backends.base import BaseCache
from django.test import TestCase, override_settings

from concordia.tests.utils import CreateTestUsers, create_asset, create_project

from ..tasks import (
    fetch_all_urls,
    get_collection_items,
    get_item_id_from_item_url,
    get_item_info_from_result,
    import_collection_task,
    import_item_count_from_url,
    import_items_into_project_from_url,
    normalize_collection_url,
    redownload_image_task,
)
from .utils import create_import_job


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


class ImportItemCountFromUrlTests(TestCase):
    def mocked_requests_get(*args, **kwargs):
        class MockResponse:
            def json(self):
                item_data = {
                    "resources": [
                        {"files": []},
                    ]
                }
                return item_data

            def raise_for_status(self):
                pass

        return MockResponse()

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.dummy.DummyCache",
            }
        }
    )
    def test_import_item_count_from_url(self, mock_get):
        self.assertEqual(import_item_count_from_url(None), ("None - Asset Count: 0", 0))

    def test_unhandled_exception_importing(self):
        self.assertRaises(Exception, import_item_count_from_url)


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
        items = get_collection_items("https://www.loc.gov/collections/example/")
        self.assertEqual(len(items), 1)

    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "importer.tests.test_tasks.MockCache",
            }
        }
    )
    def test_cache_hit(self):
        items = get_collection_items("https://www.loc.gov/collections/example/")
        self.assertEqual(len(items), 1)

    @mock.patch("importer.tasks.get_item_info_from_result")
    @mock.patch.object(requests.Session, "get")
    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.dummy.DummyCache",
            }
        }
    )
    def test_ignored_format(self, mock_get, mock_get_info):
        mock_get.return_value = MockResponse(original_format="collection")
        mock_get.return_value.url = "https://www.loc.gov/collections/example/"
        items = get_collection_items("https://www.loc.gov/collections/example/")
        self.assertEqual(len(items), 1)
        self.assertTrue(mock_get_info.called)


class FetchAllUrlsTests(TestCase):
    @mock.patch.object(concurrent.futures.ThreadPoolExecutor, "map")
    def test_fetch_all_urls(self, mock_map):
        output = "https://www.loc.gov/item/mss859430021/ - Asset Count: 0"
        mock_map.return_value = ((output, 0),)
        finals, totals = fetch_all_urls(
            [
                "https://www.loc.gov/item/mss859430021/",
            ]
        )
        self.assertEqual(finals, [output])
        self.assertEqual(totals, 0)


class ImportItemsIntoProjectFromUrlTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.login_user()
        self.project = create_project()

    def test_no_match(self):
        with self.assertRaises(ValueError):
            import_items_into_project_from_url(
                None, None, "https://www.loc.gov/resource/mss859430021/"
            )

    def test_item(self):
        import_job = import_items_into_project_from_url(
            self.user, self.project, "https://www.loc.gov/item/mss859430021/"
        )
        self.assertEqual(import_job.project, self.project)

    def test_other_url_type(self):
        import_job = import_items_into_project_from_url(
            self.user,
            self.project,
            "https://www.loc.gov/collections/branch-rickey-papers/",
        )
        self.assertEqual(import_job.project, self.project)


class ImportCollectionTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.login_user()

    @mock.patch("importer.tasks.get_collection_items")
    def test_import_collection(self, mock_get):
        magic_mock = mock.MagicMock()
        magic_mock.request = mock.MagicMock()
        magic_mock.request.id = 1
        import_job = create_import_job(created_by=self.user)
        mock_get.return_value = ((None, None),)
        import_collection_task(import_job.pk)
        self.assertTrue(mock_get.called)


class RedownloadImageTaskTests(TestCase):
    @mock.patch("importer.tasks.download_asset")
    def test_redownload_image_task(self, mock_download):
        redownload_image_task(create_asset().pk)
        self.assertTrue(mock_download.called)


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
