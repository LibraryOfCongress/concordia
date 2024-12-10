import concurrent.futures
from unittest import mock

import requests
from django.core.cache.backends.base import BaseCache
from django.test import TestCase, override_settings
from django.utils import timezone

from concordia.models import Item
from concordia.tests.utils import (
    CreateTestUsers,
    create_asset,
    create_item,
    create_project,
)
from importer import tasks
from importer.models import ImportItem, ImportJob
from importer.tasks import (
    fetch_all_urls,
    get_item_id_from_item_url,
    get_item_info_from_result,
    import_collection_task,
    import_item_count_from_url,
    import_items_into_project_from_url,
    normalize_collection_url,
    redownload_image_task,
    update_task_status,
)

from .utils import create_import_item, create_import_job


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


class TaskDecoratorTests(TestCase):
    def test_update_task_status(self):
        def test_function(self, task_status_object, raise_exception=False):
            task_status_object.test_function_ran = True
            if raise_exception:
                raise Exception("Test Exception")
            task_status_object.test_function_finished = True

        wrapped_test_function = update_task_status(test_function)

        # We create this non-mocked completed job here to use in a later test
        # because we can't easily do this once we mock ImportJob.save
        test_job = create_import_job(completed=timezone.now())

        # We can't just mock the entire model here or use easily use a custom
        # class because update_task_status depends on Django model internals,
        # particularly __class__._default_manager. __class__ cannot be overriden
        # (it points to MagicMock), Model._default_manager cannot be set directly
        # and mocking Model.objects does not cause called on Model._default_manager
        # to properly use the mock--it continues to use the actual Model.objects
        with mock.patch.multiple(
            ImportJob,
            save=mock.MagicMock(),
            __str__=mock.MagicMock(return_value="Mock Job"),
        ):
            job = ImportJob()
            wrapped_test_function(mock.MagicMock(), job)
            self.assertTrue(hasattr(job, "test_function_ran"))
            self.assertTrue(job.test_function_ran)
            self.assertTrue(hasattr(job, "test_function_finished"))
            self.assertTrue(job.test_function_finished)
            self.assertNotEqual(job.last_started, None)
            self.assertNotEqual(job.task_id, None)
            self.assertTrue(job.completed)
            self.assertTrue(job.save.called)

            ImportJob.save.reset_mock()
            job2 = ImportJob()
            job2.status = "Original Status"
            with self.assertRaisesRegex(Exception, "Test Exception"):
                wrapped_test_function(mock.MagicMock(), job2, True)
            self.assertTrue(hasattr(job2, "test_function_ran"))
            self.assertTrue(job2.test_function_ran)
            self.assertFalse(hasattr(job2, "test_function_finished"))
            self.assertNotEqual(job2.last_started, None)
            self.assertNotEqual(job2.task_id, None)
            self.assertFalse(job2.completed)
            self.assertTrue(job2.save.called)
            self.assertEqual(
                job2.status, "Original Status\n\nUnhandled exception: Test Exception"
            )

            ImportJob.save.reset_mock()
            job3 = ImportJob()
            job3.id = test_job.id
            with self.assertLogs("importer.tasks", level="WARNING") as log:
                wrapped_test_function(mock.MagicMock(), job3)
                self.assertEqual(
                    log.output,
                    [
                        "WARNING:importer.tasks:Task Mock Job was "
                        "already completed and will not be repeated"
                    ],
                )
            self.assertFalse(hasattr(job3, "test_function_ran"))
            self.assertFalse(hasattr(job3, "test_function_finished"))
            self.assertEqual(job3.last_started, None)
            self.assertEqual(job3.task_id, None)
            self.assertFalse(job3.completed)
            self.assertFalse(job3.save.called)


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
        items = tasks.get_collection_items("https://www.loc.gov/collections/example/")
        self.assertEqual(len(items), 1)

    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "importer.tests.test_tasks.MockCache",
            }
        }
    )
    def test_cache_hit(self):
        items = tasks.get_collection_items("https://www.loc.gov/collections/example/")
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
        items = tasks.get_collection_items("https://www.loc.gov/collections/example/")
        self.assertEqual(len(items), 1)
        self.assertTrue(mock_get_info.called)

    def test_no_results(self):
        with (
            mock.patch("importer.tasks.cache") as cache_mock,
            mock.patch("importer.tasks.requests_retry_session") as requests_mock,
            self.assertLogs("importer.tasks", level="ERROR") as log,
        ):
            cache_mock.get.return_value = None
            requests_mock.return_value.get.return_value.json.return_value = {}
            items = tasks.get_collection_items("http://example.com")
            self.assertEqual(items, [])
            self.assertEqual(
                log.output,
                [
                    "ERROR:importer.tasks:"
                    'Expected URL http://example.com to include "results"'
                ],
            )

    def test_get_info_exception(self):
        with (
            mock.patch("importer.tasks.cache") as cache_mock,
            mock.patch("importer.tasks.requests_retry_session") as requests_mock,
            mock.patch("importer.tasks.get_item_info_from_result") as result_mock,
            self.assertLogs("importer.tasks", level="WARNING") as log,
        ):
            cache_mock.get.return_value = None
            requests_mock.return_value.get.return_value.json.return_value = {
                "results": [1]
            }
            result_mock.side_effect = AttributeError

            items = tasks.get_collection_items("http://example.com")

            self.assertEqual(items, [])
            # The first log entry contains a stack trace, so we use assertIn
            # rather than assertEqual here
            self.assertIn(
                "WARNING:importer.tasks:"
                "Skipping result from http://example.com which did not match "
                "expected format:",
                log.output[0],
            )
            self.assertEqual(
                log.output[1],
                "WARNING:importer.tasks:"
                "No valid items found for collection url: http://example.com",
            )


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


@mock.patch("importer.tasks.requests.get")
class CreateItemImportTaskTests(TestCase):
    def setUp(self):
        self.job = create_import_job()
        self.item_url = "http://example.com"
        self.response_mock = mock.MagicMock()
        self.item_id = "testid1"
        self.item_title = "Test Title"
        self.image_url = []
        self.item_data = {
            "item": {
                "id": self.item_id,
                "title": self.item_title,
                "image_url": self.image_url,
            }
        }

    def test_create_item_import_task_http_error(self, get_mock):
        get_mock.return_value = self.response_mock
        self.response_mock.raise_for_status.side_effect = requests.exceptions.HTTPError

        with self.assertRaises(requests.exceptions.HTTPError):
            tasks.create_item_import_task(self.job.pk, self.item_url)

    def test_create_item_import_task_new_item(self, get_mock):
        get_mock.return_value = self.response_mock
        self.response_mock.json.return_value = self.item_data

        with mock.patch("importer.tasks.import_item_task.delay") as task_mock:
            tasks.create_item_import_task(self.job.pk, self.item_url)
            self.assertTrue(task_mock.called)
            self.assertEqual(Item.objects.count(), 1)
            self.assertTrue(Item.objects.filter(item_id=self.item_id).exists())

    def test_create_item_import_task_existing_item_missing_assets(self, get_mock):
        item = create_item(item_id="testid1", project=self.job.project)
        get_mock.return_value = self.response_mock
        self.response_mock.json.return_value = self.item_data

        with mock.patch(
            "importer.tasks.get_asset_urls_from_item_resources"
        ) as asset_url_mock:
            with mock.patch("importer.tasks.import_item_task.delay") as task_mock:
                with self.assertLogs("importer.tasks", level="WARNING") as log:
                    asset_url_mock.return_value = [
                        ["http://example.com/test.jpg"],
                        self.item_url,
                    ]
                    tasks.create_item_import_task(self.job.pk, self.item_url)
                    self.assertEqual(
                        log.output,
                        [
                            f"WARNING:importer.tasks:"
                            f"Reprocessing existing item {item} that is missing assets"
                        ],
                    )
                    self.assertEqual(Item.objects.count(), 1)
                    self.assertTrue(task_mock.called)

    def test_create_item_import_task_existing_item_no_missing_assets(self, get_mock):
        item = create_item(item_id="testid1", project=self.job.project)
        create_asset(item=item)
        get_mock.return_value = self.response_mock
        self.response_mock.json.return_value = self.item_data

        with mock.patch(
            "importer.tasks.get_asset_urls_from_item_resources"
        ) as asset_url_mock:
            with mock.patch("importer.tasks.import_item_task.delay") as task_mock:
                with self.assertLogs("importer.tasks", level="WARNING") as log:
                    asset_url_mock.return_value = [
                        ["http://example.com/test.jpg"],
                        self.item_url,
                    ]
                    tasks.create_item_import_task(self.job.pk, self.item_url)

                    self.assertEqual(
                        log.output,
                        [
                            f"WARNING:importer.tasks:"
                            f"Not reprocessing existing item with all asssets: {item}"
                        ],
                    )
                    self.assertEqual(
                        ImportItem.objects.get(item=item).status,
                        f"Not reprocessing existing item with all assets: {item}",
                    )
                    self.assertFalse(task_mock.called)

    def test_create_item_import_task_existing_item_redownload(self, get_mock):
        item = create_item(item_id="testid1", project=self.job.project)
        create_asset(item=item)
        get_mock.return_value = self.response_mock
        self.response_mock.json.return_value = {
            "item": {"id": "testid1", "title": "Test Title", "image_url": []}
        }

        with mock.patch(
            "importer.tasks.get_asset_urls_from_item_resources"
        ) as asset_url_mock:
            with mock.patch("importer.tasks.import_item_task.delay") as task_mock:
                asset_url_mock.return_value = [
                    ["http://example.com/test.jpg"],
                    self.item_url,
                ]
                tasks.create_item_import_task(
                    self.job.pk, self.item_url, redownload=True
                )
                self.assertTrue(task_mock.called)


class ItemImportTests(TestCase):
    def setUp(self):
        self.item_url = "http://example.com"
        self.job = create_import_job()
        self.import_item = create_import_item(import_job=self.job, url=self.item_url)

    def test_import_item_task(self):
        with mock.patch("importer.tasks.import_item") as task_mock:
            tasks.import_item_task(self.import_item.pk)
            self.assertTrue(task_mock.called)
            task, called_import_item = task_mock.call_args.args
            self.assertTrue(called_import_item, self.import_item)

    def test_import_item(self):
        with (
            mock.patch(
                "importer.tasks.get_asset_urls_from_item_resources"
            ) as asset_url_mock,
            mock.patch("importer.tasks.download_asset_task.s") as download_mock,
            mock.patch("importer.tasks.group") as group_mock,
        ):
            # It's difficult/impossible to cleanly mock a decorator due to the way
            # they're applied when the decorated object/function is evaluated on
            # import, so we unfortunately have to handle the update_task_status
            # decorator, so we need a mock object that can pass for a Celery task
            # object so update_task_status doesn't error during the test
            task_mock = mock.MagicMock()
            task_mock.request.id = "f81d4fae-7dec-11d0-a765-00a0c91e6bf6"

            asset_url_mock.return_value = [
                ["http://example.com/test.jpg"],
                self.item_url,
            ]

            tasks.import_item(task_mock, self.import_item)
            self.assertFalse(download_mock.called)
            self.assertTrue(group_mock.called)

            asset_url_mock.return_value = [
                [],
                "",
            ]

            tasks.import_item(task_mock, self.import_item)
            self.assertFalse(download_mock.called)
            self.assertTrue(group_mock.called)

    def test_populate_item_from_url(self):
        item = Item(item_url="http://example.com")
        item_info = {
            "title": "Test Title",
            "description": "Test description",
            "image_url": ["image.gif", "image.jpg", "image2.jpg"],
        }

        tasks.populate_item_from_url(item, item_info)

        self.assertEqual(item.item_url, "http://example.com")
        self.assertEqual(item.title, "Test Title")
        self.assertEqual(item.description, "Test description")
        self.assertEqual(item.thumbnail_url, "http://example.com/image.jpg")
