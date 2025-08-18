import concurrent.futures
import io
import shutil
import tempfile
import uuid
from unittest import mock

import requests
from django.core.cache import caches
from django.core.cache.backends.base import BaseCache
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Max
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from concordia.models import Asset, Item
from concordia.tests.utils import (
    CreateTestUsers,
    create_asset,
    create_item,
    create_project,
)
from configuration.models import Configuration
from importer import tasks
from importer.exceptions import ImageImportFailure
from importer.models import (
    DownloadAssetImageJob,
    ImportItem,
    ImportItemAsset,
    ImportJob,
    TaskStatusModel,
    VerifyAssetImageJob,
)
from importer.tasks import fetch_all_urls
from importer.tasks.collections import (
    import_collection_task,
    normalize_collection_url,
)
from importer.tasks.decorators import update_task_status
from importer.tasks.images import redownload_image_task
from importer.tasks.items import (
    _guess_extension,
    download_and_set_item_thumbnail,
    get_item_id_from_item_url,
    get_item_info_from_result,
    import_items_into_project_from_url,
    populate_item_from_data,
)

from .utils import (
    create_download_asset_image_job,
    create_import_asset,
    create_import_item,
    create_import_job,
    create_verify_asset_image_job,
)


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
                        "WARNING:importer.tasks.decorators:Task Mock Job was "
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
        self.assertEqual(
            tasks.items.import_item_count_from_url(None), ("None - Asset Count: 0", 0)
        )

    def test_unhandled_exception_importing(self):
        with mock.patch("importer.tasks.items.requests.get") as get_mock:
            get_mock.side_effect = AttributeError("Error message")
            self.assertEqual(
                tasks.items.import_item_count_from_url("http://example.com"),
                ("Unhandled exception importing http://example.com Error message", 0),
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


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "assets": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    },
    AWS_STORAGE_BUCKET_NAME="test-bucket",
)
class ImportItemsIntoProjectFromUrlTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.login_user()
        self.project = create_project()

    @mock.patch("importer.tasks.items.create_item_import_task.delay")
    def test_no_match(self, mock_task):
        with self.assertRaises(ValueError):
            import_items_into_project_from_url(
                None, None, "https://www.loc.gov/resource/mss859430021/"
            )
        self.assertFalse(mock_task.called)

    @mock.patch("importer.tasks.items.create_item_import_task.delay")
    def test_item(self, mock_task):
        import_job = import_items_into_project_from_url(
            self.user, self.project, "https://www.loc.gov/item/mss859430021/"
        )
        self.assertEqual(import_job.project, self.project)
        self.assertTrue(mock_task.called)

    @mock.patch("importer.tasks.collections.import_collection_task.delay")
    def test_other_url_type(self, mock_task):
        import_job = import_items_into_project_from_url(
            self.user,
            self.project,
            "https://www.loc.gov/collections/branch-rickey-papers/",
        )
        self.assertEqual(import_job.project, self.project)
        self.assertTrue(mock_task.called)
        mock_task.assert_called_with(import_job.pk, False)


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


class RedownloadImageTaskTests(TestCase):
    @mock.patch("importer.tasks.images.download_asset")
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


@mock.patch("importer.tasks.items.requests.get")
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
            tasks.items.create_item_import_task(self.job.pk, self.item_url)

    def test_create_item_import_task_new_item(self, get_mock):
        get_mock.return_value = self.response_mock
        self.response_mock.json.return_value = self.item_data

        with (
            mock.patch("importer.tasks.items.import_item_task.delay") as task_mock,
            mock.patch("importer.tasks.items.download_and_set_item_thumbnail"),
        ):
            tasks.items.create_item_import_task(self.job.pk, self.item_url)
            self.assertTrue(task_mock.called)
            self.assertEqual(Item.objects.count(), 1)
            self.assertTrue(Item.objects.filter(item_id=self.item_id).exists())

    def test_create_item_import_task_existing_item_missing_assets(self, get_mock):
        item = create_item(item_id="testid1", project=self.job.project)
        get_mock.return_value = self.response_mock
        self.response_mock.json.return_value = self.item_data

        with (
            self.assertLogs("importer.tasks", level="WARNING") as log,
            mock.patch(
                "importer.tasks.items.get_asset_urls_from_item_resources"
            ) as asset_url_mock,
            mock.patch("importer.tasks.items.import_item_task.delay") as task_mock,
            mock.patch("importer.tasks.items.download_and_set_item_thumbnail"),
        ):
            asset_url_mock.return_value = [
                ["http://example.com/test.jpg"],
                self.item_url,
            ]
            tasks.items.create_item_import_task(self.job.pk, self.item_url)
            self.assertEqual(
                log.output,
                [
                    f"WARNING:importer.tasks.items:"
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

        with (
            self.assertLogs("importer.tasks", level="WARNING") as log,
            mock.patch(
                "importer.tasks.items.get_asset_urls_from_item_resources"
            ) as asset_url_mock,
            mock.patch("importer.tasks.items.import_item_task.delay") as task_mock,
            mock.patch("importer.tasks.items.download_and_set_item_thumbnail"),
        ):
            asset_url_mock.return_value = [
                ["http://example.com/test.jpg"],
                self.item_url,
            ]
            tasks.items.create_item_import_task(self.job.pk, self.item_url)

            self.assertEqual(
                log.output,
                [
                    f"WARNING:importer.tasks.items:"
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

        with (
            mock.patch(
                "importer.tasks.items.get_asset_urls_from_item_resources"
            ) as asset_url_mock,
            mock.patch("importer.tasks.items.import_item_task.delay") as task_mock,
            mock.patch("importer.tasks.items.download_and_set_item_thumbnail"),
        ):
            asset_url_mock.return_value = [
                ["http://example.com/test.jpg"],
                self.item_url,
            ]
            tasks.items.create_item_import_task(
                self.job.pk, self.item_url, redownload=True
            )
            self.assertTrue(task_mock.called)


class ItemImportTests(TestCase):
    def setUp(self):
        self.item_url = "http://example.com"
        self.job = create_import_job()
        self.import_item = create_import_item(import_job=self.job, url=self.item_url)

    def test_import_item_task(self):
        with mock.patch("importer.tasks.items.import_item") as task_mock:
            tasks.items.import_item_task(self.import_item.pk)
            self.assertTrue(task_mock.called)
            task, called_import_item = task_mock.call_args.args
            self.assertTrue(called_import_item, self.import_item)

    def test_import_item(self):
        with (
            mock.patch(
                "importer.tasks.items.get_asset_urls_from_item_resources"
            ) as asset_url_mock,
            mock.patch("importer.tasks.assets.download_asset_task.s") as download_mock,
            mock.patch("importer.tasks.items.group") as group_mock,
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

            tasks.items.import_item(task_mock, self.import_item)
            self.assertFalse(download_mock.called)
            self.assertTrue(group_mock.called)

            # Test that it properly errors if we try to import the same item again
            self.import_item.completed = None
            self.import_item.save()
            with self.assertRaises(ValidationError):
                tasks.items.import_item(task_mock, self.import_item)

            asset_url_mock.return_value = [
                [],
                "",
            ]

            self.import_item.completed = None
            self.import_item.save()
            tasks.items.import_item(task_mock, self.import_item)
            self.assertFalse(download_mock.called)
            self.assertTrue(group_mock.called)

    def test_populate_item_from_data(self):
        item = Item(item_url="http://example.com")
        item_info = {
            "title": "Test Title",
            "description": "Test description",
            "image_url": ["image.gif", "image.jpg", "image2.jpg"],
        }

        tasks.items.populate_item_from_data(item, item_info)

        self.assertEqual(item.item_url, "http://example.com")
        self.assertEqual(item.title, "Test Title")
        self.assertEqual(item.description, "Test description")
        self.assertEqual(item.thumbnail_url, "http://example.com/image.jpg")

    def test_handles_exception_when_get_image_url_raises(self):
        item = self.import_item.item
        item.item_url = "http://example.com/"
        item.save()

        class FakeInfo:
            """Dict-like; raises on get('image_url') to hit the except branch."""

            def __init__(self):
                self._store = {
                    "title": "T",
                    "description": "D",
                    # Used by the early list-comp (outside try/except). No .jpg so
                    # it won't set thumbnail_url there either.
                    "image_url": ["http://example.com/nope.png"],
                }

            def __getitem__(self, key):
                return self._store[key]

            def get(self, key, default=None):
                if key == "image_url":
                    # Trigger the `except Exception: thumb_urls = []`
                    raise Exception("Error")
                return self._store.get(key, default)

        info = FakeInfo()
        result = populate_item_from_data(item, info)

        # Function should swallow the exception and NOT return a URL.
        self.assertIsNone(result)

        # In-memory fields are updated
        self.assertEqual(item.title, "T")
        self.assertEqual(item.description, "D")
        self.assertFalse(item.thumbnail_url)

        # but not persisted, since the function doesn't save.
        item.refresh_from_db()
        self.assertEqual(item.title, "Test Item")  # original value in DB
        self.assertFalse(item.thumbnail_url)


class AssetImportTests(TestCase):
    def setUp(self):
        for cache in caches.all():
            cache.clear()

        self.import_asset = create_import_asset(url="http://example.com")
        self.asset = self.import_asset.asset
        self.job = create_download_asset_image_job(asset=self.asset)

        # It's difficult/impossible to cleanly mock a decorator due to the way
        # they're applied when the decorated object/function is evaluated on
        # import, so we unfortunately have to handle the update_task_status
        # decorator, so we need a mock object that can pass for a Celery task
        # object so update_task_status doesn't error during the test
        self.task_mock = mock.MagicMock()
        self.task_mock.request.id = "f81d4fae-7dec-11d0-a765-00a0c91e6bf6"

        self.get_return_value = [b"chunk1", b"chunk2"]

        self.valid_hash = "097c42989a9e5d9dcced7b35ec4b0486"
        self.invalid_hash = "bad-hash"

        self.filename = self.asset.get_asset_image_filename()

        self.head_object_mock = mock.MagicMock()
        self.s3_client_mock = mock.MagicMock()
        self.s3_client_mock.head_object = self.head_object_mock

    def tearDown(self):
        for cache in caches.all():
            cache.clear()

    def test_get_asset_urls_from_item_resources_empty(self):
        self.assertEqual(tasks.items.get_asset_urls_from_item_resources([]), ([], ""))

    def test_get_asset_urls_from_item_resources_url_only(self):
        results = tasks.items.get_asset_urls_from_item_resources(
            [{"url": "http://example.com"}]
        )
        self.assertEqual(results, ([], "http://example.com"))

    def test_get_asset_urls_from_item_resources_valid(self):
        results = tasks.items.get_asset_urls_from_item_resources(
            [
                {
                    "url": "http://example.com",
                    "files": [
                        [
                            {
                                "url": "http://example.com/1.jpg",
                                "height": 1,
                                "width": 1,
                                "mimetype": "image/jpeg",
                            },
                            {"url": "http://example.com/2.jpg"},
                            {
                                "url": "http://example.com/3.jpg",
                                "height": 2,
                                "width": 2,
                                "mimetype": "image/jpeg",
                            },
                            {
                                "url": "http://example.com/4.jpg",
                                "height": 100,
                                "width": 100,
                                "mimetype": "image/gif",
                            },
                        ]
                    ],
                }
            ]
        )
        self.assertEqual(results, (["http://example.com/3.jpg"], "http://example.com"))

    def test_get_asset_urls_from_item_resources_invalid_dimension(self):
        # Because 3.jpg has invalid dimensions, it should fall back to
        # 1.jpg
        results = tasks.items.get_asset_urls_from_item_resources(
            [
                {
                    "url": "http://example.com",
                    "files": [
                        [
                            {
                                "url": "http://example.com/1.jpg",
                                "height": 1,
                                "width": 1,
                                "mimetype": "image/jpeg",
                            },
                            {"url": "http://example.com/2.jpg"},
                            {
                                "url": "http://example.com/3.jpg",
                                "height": "badnum",
                                "width": 2,
                                "mimetype": "image/jpeg",
                            },
                            {
                                "url": "http://example.com/4.jpg",
                                "height": 100,
                                "width": 100,
                                "mimetype": "image/gif",
                            },
                        ]
                    ],
                }
            ]
        )
        self.assertEqual(results, (["http://example.com/1.jpg"], "http://example.com"))

    def test_get_asset_urls_from_item_resource_no_valid(self):
        results = tasks.items.get_asset_urls_from_item_resources(
            [
                {
                    "url": "http://example.com",
                    "files": [
                        [
                            {
                                "url": "http://example.com/1.jpg",
                                "height": 1,
                                "width": 1,
                                "mimetype": "file/pdf",
                            },
                            {"url": "http://example.com/2.jpg"},
                            {
                                "url": "http://example.com/3.jpg",
                                "height": 2,
                                "width": 2,
                                "mimetype": "video/mov",
                            },
                            {
                                "url": "http://example.com/4.jpg",
                                "height": 100,
                                "width": 100,
                                "mimetype": "image/tiff",
                            },
                        ]
                    ],
                }
            ]
        )
        self.assertEqual(results, ([], "http://example.com"))

    def test_get_asset_urls_from_item_resource_no_jpgs(self):
        results = tasks.items.get_asset_urls_from_item_resources(
            [
                {
                    "url": "http://example.com",
                    "files": [
                        [
                            {
                                "url": "http://example.com/1.jpg",
                                "height": 1,
                                "width": 1,
                                "mimetype": "file/pdf",
                            },
                            {"url": "http://example.com/2.jpg"},
                            {
                                "url": "http://example.com/3.gif",
                                "height": 2,
                                "width": 2,
                                "mimetype": "image/gif",
                            },
                            {
                                "url": "http://example.com/4.gif",
                                "height": 100,
                                "width": 100,
                                "mimetype": "image/gif",
                            },
                        ]
                    ],
                }
            ]
        )
        self.assertEqual(results, (["http://example.com/4.gif"], "http://example.com"))

    def test_prefers_jp2_over_jpg_even_if_smaller(self):
        # JP2 (smaller) should win over JPG (larger) due to mimetype priority.
        results = tasks.items.get_asset_urls_from_item_resources(
            [
                {
                    "url": "http://example.com/item",
                    "files": [
                        [
                            {
                                "url": "https://tile.loc.gov/image-services/iiif/xx/j.jpg",
                                "height": 5000,
                                "width": 5000,
                                "mimetype": "image/jpeg",
                            },
                            {
                                "url": "https://tile.loc.gov/image-services/iiif/xx/jp2.jp2",
                                "height": 10,
                                "width": 10,
                                "mimetype": "image/jp2",
                            },
                        ]
                    ],
                }
            ]
        )
        self.assertEqual(
            results,
            (
                ["https://tile.loc.gov/image-services/iiif/xx/jp2.jp2"],
                "http://example.com/item",
            ),
        )

    def test_picks_largest_within_mimetype_then_service_tie(self):
        # Two JP2s: different resolutions and different services.
        # Largest resolution wins; if tied, service breaks the tie.
        results = tasks.items.get_asset_urls_from_item_resources(
            [
                {
                    "url": "http://example.com/item",
                    "files": [
                        [
                            # image-services JP2 (larger)
                            {
                                "url": "https://tile.loc.gov/image-services/iiif/xx/a.jp2",
                                "height": 200,
                                "width": 200,
                                "mimetype": "image/jp2",
                            },
                            # storage-services JP2 (smaller)
                            {
                                "url": "https://tile.loc.gov/storage-services/xx/b.jp2",
                                "height": 100,
                                "width": 100,
                                "mimetype": "image/jp2",
                            },
                        ]
                    ],
                }
            ]
        )
        self.assertEqual(
            results,
            (
                ["https://tile.loc.gov/image-services/iiif/xx/a.jp2"],
                "http://example.com/item",
            ),
        )

        # Now make them the same resolution, so storage-services should win.
        results = tasks.items.get_asset_urls_from_item_resources(
            [
                {
                    "url": "http://example.com/item2",
                    "files": [
                        [
                            {
                                "url": "https://tile.loc.gov/image-services/iiif/xx/c.jp2",
                                "height": 300,
                                "width": 300,
                                "mimetype": "image/jp2",
                            },
                            {
                                "url": "https://tile.loc.gov/storage-services/xx/d.jp2",
                                "height": 300,
                                "width": 300,
                                "mimetype": "image/jp2",
                            },
                        ]
                    ],
                }
            ]
        )
        self.assertEqual(
            results,
            (
                ["https://tile.loc.gov/storage-services/xx/d.jp2"],
                "http://example.com/item2",
            ),
        )

    def test_falls_back_to_jpg_then_gif_and_picks_largest(self):
        # No JP2, then choose largest JPG; if no JPG, then choose largest GIF.
        # Also prove that service preference does not override resolution
        # across mimetypes.
        results = tasks.items.get_asset_urls_from_item_resources(
            [
                {
                    "url": "http://example.com/r1",
                    "files": [
                        [
                            # JPG candidates only
                            {
                                "url": "https://tile.loc.gov/storage-services/xx/large.jpg",
                                "height": 1000,
                                "width": 1000,
                                "mimetype": "image/jpeg",
                            },
                            {
                                "url": "https://tile.loc.gov/image-services/iiif/xx/small.jpg",
                                "height": 10,
                                "width": 10,
                                "mimetype": "image/jpeg",
                            },
                            # A huge GIF should still lose to JPG
                            # due to mimetype priority.
                            {
                                "url": "https://tile.loc.gov/storage-services/xx/huge.gif",
                                "height": 10000,
                                "width": 10000,
                                "mimetype": "image/gif",
                            },
                        ]
                    ],
                },
                {
                    "url": "http://example.com/r2",
                    "files": [
                        [
                            # No JP2/JPG here, so fall back to largest GIF
                            {
                                "url": "https://tile.loc.gov/image-services/iiif/xx/a.gif",
                                "height": 5,
                                "width": 5,
                                "mimetype": "image/gif",
                            },
                            {
                                "url": "https://tile.loc.gov/storage-services/xx/b.gif",
                                "height": 6,
                                "width": 6,
                                "mimetype": "image/gif",
                            },
                        ]
                    ],
                },
            ]
        )
        self.assertEqual(
            results,
            (
                [
                    "https://tile.loc.gov/storage-services/xx/large.jpg",
                    "https://tile.loc.gov/storage-services/xx/b.gif",
                ],
                "http://example.com/r1",
            ),
        )

    def test_service_tie_breaker_unknown_service_is_last(self):
        # Tie on resolution within the same mimetype across three services:
        # storage-services should win over image-services, which should
        # win over unknown.
        results = tasks.items.get_asset_urls_from_item_resources(
            [
                {
                    "url": "http://example.com/item",
                    "files": [
                        [
                            {
                                "url": "https://unknown.example.com/path/x.jpg",
                                "height": 100,
                                "width": 100,
                                "mimetype": "image/jpeg",
                            },
                            {
                                "url": "https://tile.loc.gov/image-services/iiif/xx/y.jpg",
                                "height": 100,
                                "width": 100,
                                "mimetype": "image/jpeg",
                            },
                            {
                                "url": "https://tile.loc.gov/storage-services/xx/z.jpg",
                                "height": 100,
                                "width": 100,
                                "mimetype": "image/jpeg",
                            },
                        ]
                    ],
                }
            ]
        )
        self.assertEqual(
            results,
            (
                ["https://tile.loc.gov/storage-services/xx/z.jpg"],
                "http://example.com/item",
            ),
        )

    def test_ignores_variants_missing_fields_and_unknown_mimetype(self):
        # Mix of invalid variants and one valid target.
        results = tasks.items.get_asset_urls_from_item_resources(
            [
                {
                    "url": "http://example.com/item",
                    "files": [
                        [
                            # Missing width
                            {
                                "url": "https://tile.loc.gov/storage-services/xx/misswidth.jpg",
                                "height": 10,
                                "mimetype": "image/jpeg",
                            },
                            # Missing height
                            {
                                "url": "https://tile.loc.gov/storage-services/xx/missheight.jpg",
                                "width": 10,
                                "mimetype": "image/jpeg",
                            },
                            # Missing url
                            {
                                "height": 10,
                                "width": 10,
                                "mimetype": "image/jpeg",
                            },
                            # Unknown mimetype
                            {
                                "url": "https://tile.loc.gov/storage-services/xx/wrong.tif",
                                "height": 10,
                                "width": 10,
                                "mimetype": "image/tiff",
                            },
                            # Valid GIF (only valid one)
                            {
                                "url": "https://tile.loc.gov/image-services/iiif/xx/ok.gif",
                                "height": 2,
                                "width": 3,
                                "mimetype": "image/gif",
                            },
                        ]
                    ],
                }
            ]
        )
        self.assertEqual(
            results,
            (
                ["https://tile.loc.gov/image-services/iiif/xx/ok.gif"],
                "http://example.com/item",
            ),
        )

    def test_first_resource_missing_url_key_sets_empty_item_resource_url(self):
        results = tasks.items.get_asset_urls_from_item_resources(
            [
                {
                    # No "url" key
                    "files": [
                        [
                            {
                                "url": "https://tile.loc.gov/storage-services/xx/aa.jp2",
                                "height": 5,
                                "width": 5,
                                "mimetype": "image/jp2",
                            }
                        ]
                    ],
                },
                {
                    "url": "http://example.com/second",
                    "files": [
                        [
                            {
                                "url": "https://tile.loc.gov/image-services/iiif/xx/bb.jpg",
                                "height": 10,
                                "width": 10,
                                "mimetype": "image/jpeg",
                            }
                        ]
                    ],
                },
            ]
        )
        self.assertEqual(
            results,
            (
                [
                    "https://tile.loc.gov/storage-services/xx/aa.jp2",
                    "https://tile.loc.gov/image-services/iiif/xx/bb.jpg",
                ],
                "",
            ),
        )

    def test_download_asset_task(self):
        with mock.patch("importer.tasks.assets.download_asset") as task_mock:
            tasks.assets.download_asset_task(self.import_asset.pk)
            self.assertTrue(task_mock.called)
            task, called_import_asset = task_mock.call_args.args
            self.assertTrue(called_import_asset, self.import_asset)

            # Test sending a bad pk
            task_mock.reset_mock()
            max_pk = ImportItemAsset.objects.aggregate(Max("pk"))["pk__max"]
            with self.assertRaises(ImportItemAsset.DoesNotExist):
                tasks.assets.download_asset_task(max_pk + 1)
            self.assertFalse(task_mock.called)

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            "assets": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        },
        AWS_STORAGE_BUCKET_NAME="test-bucket",
    )
    def test_download_asset_valid(self):
        with (
            mock.patch("importer.tasks.assets.requests.get") as get_mock,
            mock.patch("importer.tasks.assets.boto3.client") as boto_mock,
            mock.patch("importer.tasks.assets.flag_enabled") as flag_mock,
        ):
            get_mock.return_value.iter_content.return_value = self.get_return_value
            boto_mock.return_value = self.s3_client_mock
            flag_mock.return_value = True
            self.head_object_mock.return_value = {"ETag": f'"{self.valid_hash}"'}

            tasks.assets.download_asset(self.task_mock, self.import_asset)

            self.assertEqual(get_mock.call_args[0], ("http://example.com",))
            self.assertTrue(get_mock.call_args[1]["stream"])

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            "assets": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        },
        AWS_STORAGE_BUCKET_NAME="test-bucket",
    )
    def test_download_asset_valid_checksum_fail(self):
        with (
            mock.patch("importer.tasks.assets.requests.get") as get_mock,
            mock.patch("importer.tasks.assets.boto3.client") as boto_mock,
            mock.patch("importer.tasks.assets.flag_enabled") as flag_mock,
        ):
            get_mock.return_value.iter_content.return_value = self.get_return_value
            boto_mock.return_value = self.s3_client_mock
            flag_mock.return_value = True
            self.head_object_mock.return_value = {"ETag": f'"{self.invalid_hash}"'}

            with self.assertRaises(Exception) as assertion:
                tasks.assets.download_asset(self.task_mock, self.import_asset)

            self.assertEqual(
                str(assertion.exception),
                f"ETag {self.invalid_hash} for {self.filename} did not match "
                f"calculated md5 hash {self.valid_hash}",
            )

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            "assets": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        },
        AWS_STORAGE_BUCKET_NAME="test-bucket",
    )
    def test_download_asset_valid_checksum_fail_without_flag(self):
        with (
            mock.patch("importer.tasks.assets.requests.get") as get_mock,
            mock.patch("importer.tasks.assets.boto3.client") as boto_mock,
            self.assertLogs("importer.tasks", level="WARN") as log,
        ):
            get_mock.return_value.iter_content.return_value = self.get_return_value
            boto_mock.return_value = self.s3_client_mock
            self.head_object_mock.return_value = {"ETag": f'"{self.invalid_hash}"'}

            tasks.assets.download_asset(self.task_mock, self.import_asset)
            self.assertEqual(
                log.output[0],
                f"WARNING:importer.tasks.assets:ETag ({self.invalid_hash}) for "
                f"{self.filename} did not match calculated md5 hash "
                f"({self.valid_hash}) but the IMPORT_IMAGE_CHECKSUM flag is disabled",
            )

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            "assets": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        },
        AWS_STORAGE_BUCKET_NAME="test-bucket",
    )
    def test_download_asset_invalid(self):
        with (
            mock.patch("importer.tasks.assets.requests.get") as get_mock,
            self.assertLogs("importer.tasks", level="ERROR") as log,
        ):
            get_mock.return_value.raise_for_status.side_effect = AttributeError
            with self.assertRaises(ImageImportFailure):
                tasks.assets.download_asset(self.task_mock, self.import_asset)
            # Since the logging includes a stacktrace, we just check the
            # beginning of the log entry with assertIn
            self.assertIn(
                "ERROR:importer.tasks.assets:"
                "Unable to download http://example.com to "
                "test-campaign/test-project/testitem.0123456789/1.jpg",
                log.output[0],
            )

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            "assets": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        },
        AWS_STORAGE_BUCKET_NAME="test-bucket",
    )
    def test_download_asset_retry_success(self):
        import_asset = self.import_asset
        import_asset.failed = timezone.now()
        import_asset.completed = None
        import_asset.failure_reason = TaskStatusModel.FailureReason.IMAGE
        import_asset.status = "Test failed status"
        import_asset.retry_count = 0
        import_asset.failure_history = []
        import_asset.save()

        with mock.patch(
            "importer.models.tasks.assets.download_asset_task"
        ) as task_mock:
            response = import_asset.retry_if_possible()

            self.assertNotEqual(response, False)
            self.assertTrue(task_mock.apply_async.called)
            self.assertEqual(len(import_asset.failure_history), 1)
            self.assertEqual(import_asset.failed, None)
            self.assertEqual(import_asset.retry_count, 1)
            self.assertEqual(import_asset.failure_reason, "")

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            "assets": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        },
        AWS_STORAGE_BUCKET_NAME="test-bucket",
    )
    def test_download_asset_retry_maximum_exceeded(self):
        try:
            config = Configuration.objects.get(key="asset_image_import_max_retries")
            config.value = "1"
            config.data_type = Configuration.DataType.NUMBER
            config.save()
        except Configuration.DoesNotExist:
            Configuration.objects.create(
                key="asset_image_import_max_retries",
                value="1",
                data_type=Configuration.DataType.NUMBER,
            )

        import_asset = self.import_asset
        import_asset.failed = timezone.now()
        import_asset.completed = None
        import_asset.failure_reason = TaskStatusModel.FailureReason.IMAGE
        import_asset.status = "Test failed status"
        import_asset.retry_count = 1
        import_asset.failure_history = []
        import_asset.save()

        with mock.patch(
            "importer.models.tasks.assets.download_asset_task"
        ) as task_mock:
            response = import_asset.retry_if_possible()

            self.assertFalse(response)
            self.assertFalse(task_mock.apply_async.called)
            self.assertEqual(len(import_asset.failure_history), 1)
            self.assertNotEqual(import_asset.failed, None)
            self.assertEqual(
                import_asset.status,
                "Maximum number of retries reached while retrying image download "
                "for asset. The failure reason before retrying was Image and the "
                "status was Test failed status",
            )
            self.assertEqual(import_asset.retry_count, 1)
            self.assertEqual(
                import_asset.failure_reason, TaskStatusModel.FailureReason.RETRIES
            )

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            "assets": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        },
        AWS_STORAGE_BUCKET_NAME="test-bucket",
    )
    def test_download_asset_retry_cant_reset(self):
        import_asset = self.import_asset
        import_asset.completed = None
        import_asset.failure_reason = TaskStatusModel.FailureReason.IMAGE
        import_asset.status = "Test failed status"
        import_asset.retry_count = 0
        import_asset.failure_history = []
        import_asset.save()

        with mock.patch(
            "importer.models.tasks.assets.download_asset_task"
        ) as task_mock:
            response = import_asset.retry_if_possible()

            self.assertFalse(response)
            self.assertFalse(task_mock.apply_async.called)
            self.assertNotEqual(import_asset.status, "Test failed status")
            self.assertEqual(len(import_asset.failure_history), 0)
            self.assertEqual(import_asset.failed, None)
            self.assertEqual(import_asset.retry_count, 0)
            self.assertEqual(
                import_asset.failure_reason, TaskStatusModel.FailureReason.IMAGE
            )

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            "assets": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        },
        AWS_STORAGE_BUCKET_NAME="test-bucket",
    )
    def test_download_asset_retry_invalid_failure_reason(self):
        import_asset = self.import_asset
        import_asset.failed = timezone.now()
        import_asset.completed = None
        import_asset.failure_reason = ""
        import_asset.status = "Test failed status"
        import_asset.retry_count = 0
        import_asset.failure_history = []
        import_asset.save()

        with mock.patch(
            "importer.models.tasks.assets.download_asset_task"
        ) as task_mock:
            response = import_asset.retry_if_possible()

            self.assertFalse(response)
            self.assertFalse(task_mock.apply_async.called)
            self.assertEqual(import_asset.status, "Test failed status")
            self.assertEqual(len(import_asset.failure_history), 0)
            self.assertNotEqual(import_asset.failed, None)
            self.assertEqual(import_asset.retry_count, 0)
            self.assertEqual(import_asset.failure_reason, "")

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            "assets": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        },
        AWS_STORAGE_BUCKET_NAME="test-bucket",
    )
    def test_download_asset_manual_retry_success(self):
        # This mimics an admin manually retrying the task, rather than
        # the automatic retry system (such as through an admin action).
        # We want to be sure the failure information is correctly reset.
        import_asset = self.import_asset
        import_asset.failed = timezone.now()
        import_asset.completed = None
        import_asset.failure_reason = ""
        import_asset.status = "Test failed status"
        import_asset.retry_count = 0
        import_asset.failure_history = []
        import_asset.save()

        with mock.patch(
            "importer.models.tasks.assets.download_and_store_asset_image"
        ) as download_mock:
            download_mock.return_value = "image.jpg"
            tasks.assets.download_asset_task.delay(import_asset.pk)
            import_asset.refresh_from_db()
            self.assertTrue(download_mock.called)
            self.assertEqual(import_asset.status, "Completed")
            self.assertEqual(len(import_asset.failure_history), 0)
            self.assertEqual(import_asset.failed, None)
            self.assertEqual(import_asset.retry_count, 0)
            self.assertEqual(import_asset.failure_reason, "")

    @mock.patch("importer.tasks.assets.download_and_store_asset_image")
    @mock.patch("importer.tasks.assets.logger.info")
    def test_download_url_from_asset(self, mock_logger, mock_download):
        self.asset.download_url = "https://example.com/image.png"
        self.asset.save()
        self.job.refresh_from_db()

        mock_download.return_value = "stored_image.png"

        tasks.assets.download_asset(self.task_mock, self.job)

        mock_download.assert_called_once_with(self.asset.download_url, mock.ANY)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.storage_image, "stored_image.png")
        mock_logger.assert_any_call(
            "Download and storage of asset image %s complete. Setting storage_image "
            "on asset %s (%s)",
            "stored_image.png",
            self.asset,
            self.asset.id,
        )

    @mock.patch("importer.tasks.assets.download_and_store_asset_image")
    @mock.patch("importer.tasks.assets.logger.info")
    def test_valid_file_extension(self, mock_logger, mock_download):
        self.asset.download_url = "https://example.com/image.png"
        self.asset.save()
        self.job.refresh_from_db()

        mock_download.return_value = "stored_image.png"
        tasks.assets.download_asset(self.task_mock, self.job)

        asset_image_filename = self.asset.get_asset_image_filename("png")
        mock_download.assert_called_once_with(
            self.asset.download_url, asset_image_filename
        )

        self.asset.refresh_from_db()
        self.assertEqual(self.asset.storage_image, "stored_image.png")
        mock_logger.assert_any_call(
            "Download and storage of asset image %s complete. Setting storage_image "
            "on asset %s (%s)",
            "stored_image.png",
            self.asset,
            self.asset.id,
        )


class BatchVerifyAssetImagesTaskCallbackTests(TestCase):
    def setUp(self):
        self.batch_id = uuid.uuid4()
        self.concurrency = 5

    @mock.patch("importer.tasks.images.batch_verify_asset_images_task.delay")
    def test_no_failures_detected_no_failures_in_results(self, mock_task):
        results = [True, True, True]
        tasks.images.batch_verify_asset_images_task_callback(
            results, self.batch_id, self.concurrency, False
        )
        mock_task.assert_called_once_with(self.batch_id, self.concurrency, False)

    @mock.patch("importer.tasks.images.batch_verify_asset_images_task.delay")
    def test_no_failures_detected_some_failures_in_results(self, mock_task):
        results = [True, False, True]
        with self.assertLogs("importer.tasks", level="INFO") as log:
            tasks.images.batch_verify_asset_images_task_callback(
                results, self.batch_id, self.concurrency, False
            )
            self.assertIn(
                "INFO:importer.tasks.images:At least one verification "
                f"failure detected for batch {self.batch_id}",
                log.output,
            )
        mock_task.assert_called_once_with(self.batch_id, self.concurrency, True)

    @mock.patch("importer.tasks.images.batch_verify_asset_images_task.delay")
    def test_failures_already_detected(self, mock_task):
        results = [True, False, True]
        tasks.images.batch_verify_asset_images_task_callback(
            results, self.batch_id, self.concurrency, True
        )
        mock_task.assert_called_once_with(self.batch_id, self.concurrency, True)


class BatchVerifyAssetImagesTaskTests(TestCase):
    def setUp(self):
        self.batch_id = uuid.uuid4()
        self.concurrency = 2
        asset1 = create_asset()
        asset2 = create_asset(item=asset1.item, slug="test-asset-2")
        self.job1 = create_verify_asset_image_job(batch=self.batch_id, asset=asset1)
        self.job2 = create_verify_asset_image_job(batch=self.batch_id, asset=asset2)

    @mock.patch("importer.tasks.images.logger.info")
    @mock.patch("importer.tasks.images.batch_download_asset_images_task")
    def test_no_jobs_remaining_with_failures(self, mock_batch_download, mock_logger):
        VerifyAssetImageJob.objects.all().delete()
        tasks.images.batch_verify_asset_images_task(
            self.batch_id, self.concurrency, True
        )
        mock_logger.assert_any_call(
            "Failures in VerifyAssetImageJobs in batch %s detected, so starting "
            "DownloadAssetImageJob batch",
            self.batch_id,
        )
        mock_batch_download.assert_called_once_with(self.batch_id, self.concurrency)

    @mock.patch("importer.tasks.images.logger.info")
    def test_no_jobs_remaining_no_failures(self, mock_logger):
        VerifyAssetImageJob.objects.all().delete()
        tasks.images.batch_verify_asset_images_task(
            self.batch_id, self.concurrency, False
        )
        mock_logger.assert_any_call(
            "No failures in VerifyAssetImageJob batch %s. Ending task.", self.batch_id
        )

    @mock.patch("importer.tasks.images.chord")
    @mock.patch("importer.tasks.images.verify_asset_image_task.s")
    def test_jobs_remaining(self, mock_task_s, mock_chord):
        tasks.images.batch_verify_asset_images_task(
            self.batch_id, self.concurrency, False
        )
        self.assertEqual(mock_task_s.call_count, 2)
        mock_chord.assert_called()


class VerifyAssetImageTaskTests(TestCase):
    def setUp(self):
        self.asset = create_asset()
        self.batch_id = uuid.uuid4()

    @mock.patch("importer.tasks.images.logger.exception")
    def test_asset_not_found(self, mock_logger):
        with self.assertRaises(Asset.DoesNotExist):
            tasks.images.verify_asset_image_task(999)
        mock_logger.assert_called()

    @mock.patch("importer.tasks.images.logger.exception")
    def test_verify_job_not_found(self, mock_logger):
        with self.assertRaises(VerifyAssetImageJob.DoesNotExist):
            tasks.images.verify_asset_image_task(
                self.asset.pk, self.batch_id, create_job=False
            )
        mock_logger.assert_called()

    @mock.patch("importer.tasks.images.verify_asset_image")
    def test_verify_asset_image_task_success(self, mock_verify):
        job = create_verify_asset_image_job(asset=self.asset, batch=self.batch_id)
        mock_verify.return_value = True

        result = tasks.images.verify_asset_image_task(self.asset.pk, self.batch_id)
        self.assertTrue(result)
        job.refresh_from_db()
        self.assertEqual(job.status, "Storage image verified")

    @mock.patch("importer.tasks.images.verify_asset_image")
    def test_verify_asset_image_task_failure(self, mock_verify):
        job = create_verify_asset_image_job(asset=self.asset, batch=self.batch_id)
        mock_verify.return_value = False

        result = tasks.images.verify_asset_image_task(self.asset.pk, self.batch_id)
        self.assertFalse(result)
        job.refresh_from_db()
        self.assertNotEqual(job.status, "Storage image verified")

    @mock.patch("importer.tasks.images.verify_asset_image")
    def test_create_verify_asset_image_job(self, mock_verify):
        mock_verify.return_value = True
        result = tasks.images.verify_asset_image_task(
            self.asset.pk, self.batch_id, create_job=True
        )
        self.assertTrue(result)
        self.assertTrue(
            VerifyAssetImageJob.objects.filter(
                asset=self.asset, batch=self.batch_id
            ).exists()
        )

    @mock.patch("importer.tasks.images.verify_asset_image")
    def test_http_error_retries(self, mock_verify):
        create_verify_asset_image_job(asset=self.asset, batch=self.batch_id)
        mock_verify.side_effect = requests.exceptions.HTTPError("HTTP Error Occurred")
        with self.assertRaises(requests.exceptions.HTTPError):
            tasks.images.verify_asset_image_task(self.asset.pk, self.batch_id)


class CreateDownloadAssetImageJobTests(TestCase):
    def setUp(self):
        self.asset = create_asset()
        self.batch_id = uuid.uuid4()

    def test_create_new_job(self):
        tasks.images.create_download_asset_image_job(self.asset, self.batch_id)
        self.assertTrue(
            DownloadAssetImageJob.objects.filter(
                asset=self.asset, batch=self.batch_id
            ).exists()
        )

    def test_existing_uncompleted_job_not_duplicated(self):
        create_download_asset_image_job(asset=self.asset, batch=self.batch_id)
        tasks.images.create_download_asset_image_job(self.asset, self.batch_id)
        job_count = DownloadAssetImageJob.objects.filter(
            asset=self.asset, batch=self.batch_id
        ).count()
        self.assertEqual(job_count, 1)

    def test_create_new_job_if_previous_failed(self):
        failed_job = create_download_asset_image_job(
            asset=self.asset, batch=self.batch_id
        )
        failed_job.failed = timezone.now()
        failed_job.save()

        new_batch = uuid.uuid4()

        tasks.images.create_download_asset_image_job(self.asset, new_batch)
        job_count = DownloadAssetImageJob.objects.filter(asset=self.asset).count()
        self.assertEqual(job_count, 2)


class VerifyAssetImageTests(TestCase):
    def setUp(self):
        self.asset = create_asset()
        self.job = create_verify_asset_image_job(asset=self.asset)
        self.mock_task = mock.MagicMock()
        self.mock_task.request.id = uuid.uuid4()

    @mock.patch("importer.tasks.images.logger.info")
    @mock.patch("importer.tasks.images.create_download_asset_image_job")
    def test_no_storage_image(self, mock_create_job, mock_logger):
        # Use update in order to avoid the validation of storage_image, since this is
        # an invalid value, but we have to account for it
        Asset.objects.filter(id=self.asset.id).update(storage_image="")
        # We need to update the job from the database to get rid of the cached asset
        self.job.refresh_from_db()

        result = tasks.images.verify_asset_image(self.mock_task, self.job)
        self.assertFalse(result)
        mock_create_job.assert_called_once_with(self.asset, self.job.batch)
        mock_logger.assert_any_call(
            f"No storage image set on {self.asset} ({self.asset.id})"
        )

    @mock.patch("importer.tasks.images.logger.info")
    @mock.patch("importer.tasks.images.create_download_asset_image_job")
    @mock.patch("importer.tasks.images.ASSET_STORAGE.exists", return_value=False)
    def test_storage_image_missing(self, mock_exists, mock_create_job, mock_logger):
        result = tasks.images.verify_asset_image(self.mock_task, self.job)
        self.assertFalse(result)
        mock_create_job.assert_called_once_with(self.asset, self.job.batch)
        mock_logger.assert_any_call(
            f"Storage image for {self.asset} ({self.asset.id}) missing from storage"
        )

    @mock.patch("importer.tasks.images.logger.info")
    @mock.patch("importer.tasks.images.create_download_asset_image_job")
    @mock.patch("importer.tasks.images.ASSET_STORAGE.exists", return_value=True)
    @mock.patch("importer.tasks.images.ASSET_STORAGE.open")
    @mock.patch(
        "importer.tasks.images.Image.open",
        side_effect=UnidentifiedImageError("Invalid image format"),
    )
    def test_storage_image_invalid(
        self, mock_image_open, mock_open, mock_exists, mock_create_job, mock_logger
    ):
        result = tasks.images.verify_asset_image(self.mock_task, self.job)
        self.assertFalse(result)
        mock_create_job.assert_called_once_with(self.asset, self.job.batch)
        mock_logger.assert_any_call(
            f"Storage image for {self.asset} ({self.asset.id}), "
            f"{self.asset.storage_image.name}, is corrupt. The exception "
            "raised was Type: UnidentifiedImageError, Message: Invalid image format"
        )

    @mock.patch("importer.tasks.images.logger.info")
    @mock.patch("importer.tasks.images.create_download_asset_image_job")
    @mock.patch("importer.tasks.images.ASSET_STORAGE.exists", return_value=True)
    @mock.patch("importer.tasks.images.ASSET_STORAGE.open")
    @mock.patch("importer.tasks.images.Image.open")
    def test_storage_image_verify_fail(
        self, mock_image_open, mock_open, mock_exists, mock_create_job, mock_logger
    ):
        mock_image = mock.MagicMock()
        mock_image.verify.side_effect = UnidentifiedImageError("Invalid image format")
        mock_image_open.return_value.__enter__.return_value = mock_image

        result = tasks.images.verify_asset_image(self.mock_task, self.job)
        self.assertFalse(result)
        mock_create_job.assert_called_once_with(self.asset, self.job.batch)
        mock_logger.assert_any_call(
            f"Storage image for {self.asset} ({self.asset.id}), "
            f"{self.asset.storage_image.name}, is corrupt. The exception "
            "raised was Type: UnidentifiedImageError, Message: Invalid image format"
        )

    @mock.patch("importer.tasks.images.logger.info")
    @mock.patch("importer.tasks.images.ASSET_STORAGE.exists", return_value=True)
    @mock.patch("importer.tasks.images.ASSET_STORAGE.open")
    @mock.patch("importer.tasks.images.Image.open")
    def test_storage_image_verification_success(
        self, mock_image_open, mock_open, mock_exists, mock_logger
    ):
        mock_image = mock.MagicMock()
        mock_image.verify.return_value = None
        mock_image_open.return_value.__enter__.return_value = mock_image

        result = tasks.images.verify_asset_image(self.mock_task, self.job)
        self.assertTrue(result)
        mock_logger.assert_any_call(
            "Storage image for %s (%s), %s, verified successfully",
            self.asset,
            self.asset.id,
            self.asset.storage_image.name,
        )


class BatchDownloadAssetImagesTaskCallbackTests(TestCase):
    def setUp(self):
        self.batch_id = uuid.uuid4()
        self.concurrency = 5

    @mock.patch("importer.tasks.images.batch_download_asset_images_task.delay")
    def test_callback_triggers_next_batch(self, mock_task):
        results = [True, False, True]

        tasks.images.batch_download_asset_images_task_callback(
            results, self.batch_id, self.concurrency
        )

        mock_task.assert_called_once_with(self.batch_id, self.concurrency)

    @mock.patch("importer.tasks.images.batch_download_asset_images_task.delay")
    def test_callback_with_no_results(self, mock_task):
        results = []

        tasks.images.batch_download_asset_images_task_callback(
            results, self.batch_id, self.concurrency
        )

        mock_task.assert_called_once_with(self.batch_id, self.concurrency)

    @mock.patch("importer.tasks.images.batch_download_asset_images_task.delay")
    def test_callback_with_all_successful_results(self, mock_task):
        results = [True, True, True]

        tasks.images.batch_download_asset_images_task_callback(
            results, self.batch_id, self.concurrency
        )

        mock_task.assert_called_once_with(self.batch_id, self.concurrency)


class BatchDownloadAssetImagesTaskTests(TestCase):
    def setUp(self):
        self.batch_id = uuid.uuid4()
        self.concurrency = 3
        asset1 = create_asset()
        asset2 = create_asset(item=asset1.item, slug="test-asset-2")
        asset3 = create_asset(item=asset1.item, slug="test-asset-3")
        self.job1 = create_download_asset_image_job(batch=self.batch_id, asset=asset1)
        self.job2 = create_download_asset_image_job(batch=self.batch_id, asset=asset2)
        self.job3 = create_download_asset_image_job(batch=self.batch_id, asset=asset3)

    @mock.patch("importer.tasks.images.logger.info")
    @mock.patch("importer.tasks.images.chord")
    @mock.patch("importer.tasks.images.download_asset_image_task.s")
    def test_jobs_remaining(self, mock_task_s, mock_chord, mock_logger):
        tasks.images.batch_download_asset_images_task(self.batch_id, self.concurrency)
        self.assertEqual(mock_task_s.call_count, 3)
        mock_chord.assert_called()
        mock_logger.assert_any_call(
            "Processing next %s DownloadAssetImageJobs for batch %s",
            self.concurrency,
            self.batch_id,
        )

    @mock.patch("importer.tasks.images.logger.info")
    def test_no_jobs_remaining(self, mock_logger):
        DownloadAssetImageJob.objects.all().delete()
        tasks.images.batch_download_asset_images_task(self.batch_id, self.concurrency)
        mock_logger.assert_any_call(
            "No DownloadAssetImageJobs found for batch %s", self.batch_id
        )


class DownloadAssetImageTaskTests(TestCase):
    def setUp(self):
        self.asset = create_asset()
        self.batch_id = uuid.uuid4()

    @mock.patch("importer.tasks.images.logger.exception")
    def test_asset_not_found(self, mock_logger):
        with self.assertRaises(Asset.DoesNotExist):
            tasks.images.download_asset_image_task(999)
        mock_logger.assert_called()

    @mock.patch("importer.tasks.images.logger.exception")
    def test_download_job_not_found(self, mock_logger):
        with self.assertRaises(DownloadAssetImageJob.DoesNotExist):
            tasks.images.download_asset_image_task(
                self.asset.pk, self.batch_id, create_job=False
            )
        mock_logger.assert_called()

    @mock.patch("importer.tasks.images.download_asset")
    def test_download_asset_image_task_success(self, mock_download):
        create_download_asset_image_job(asset=self.asset, batch=self.batch_id)
        mock_download.return_value = "Download successful"

        result = tasks.images.download_asset_image_task(self.asset.pk, self.batch_id)
        self.assertEqual(result, "Download successful")

    @mock.patch("importer.tasks.images.download_asset")
    def test_create_download_asset_image_job(self, mock_download):
        mock_download.return_value = "Download successful"
        result = tasks.images.download_asset_image_task(
            self.asset.pk, self.batch_id, create_job=True
        )
        self.assertEqual(result, "Download successful")
        self.assertTrue(
            DownloadAssetImageJob.objects.filter(
                asset=self.asset, batch=self.batch_id
            ).exists()
        )

    @mock.patch("importer.tasks.images.download_asset")
    def test_http_error_retries(self, mock_download):
        mock_download.side_effect = requests.exceptions.HTTPError("HTTP Error Occurred")
        with self.assertRaises(requests.exceptions.HTTPError):
            tasks.images.download_asset_image_task(
                self.asset.pk, self.batch_id, create_job=True
            )


@override_settings(DEFAULT_FILE_STORAGE="django.core.files.storage.FileSystemStorage")
class DownloadItemThumbnailTests(TestCase):
    class FakeResponse:
        """Minimal streamable response for mocking requests.get(...)."""

        def __init__(self, content, content_type="image/png", on_iter=None):
            self.headers = {"Content-Type": content_type} if content_type else {}
            self._content = content
            self._on_iter = on_iter
            self._iter_called = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def raise_for_status(self):
            return

        def iter_content(self, chunk_size=64 * 1024):
            if self._on_iter and not self._iter_called:
                self._on_iter()
                self._iter_called = True
            yield self._content

    def setUp(self):
        self.temp_media = tempfile.mkdtemp(prefix="test-media-")
        self._override = override_settings(MEDIA_ROOT=self.temp_media)
        self._override.enable()

    def tearDown(self):
        self._override.disable()
        shutil.rmtree(self.temp_media, ignore_errors=True)

    def make_image_bytes(self, fmt="PNG", size=(2, 2), color=(1, 2, 3)):
        buf = io.BytesIO()
        img = Image.new("RGB", size, color)
        img.save(buf, format=fmt)
        return buf.getvalue()

    def test_skip_when_already_present_and_not_force(self):
        item = create_item()
        # Seed an existing thumbnail
        item.thumbnail_image.save("existing.jpg", ContentFile(b"old"), save=True)
        with mock.patch("importer.tasks.items.requests.get") as get_mock:
            msg = download_and_set_item_thumbnail(item, "https://example.com/test.jpg")
        self.assertIn("skipping", msg.lower())
        self.assertFalse(get_mock.called)
        item.refresh_from_db()
        self.assertTrue(item.thumbnail_image.name.endswith("existing.jpg"))
        self.assertTrue(default_storage.exists(item.thumbnail_image.name))

    def test_success_with_content_type_extension(self):
        item = create_item()
        payload = self.make_image_bytes(fmt="PNG")
        url = "https://example.com/path/name.png"
        with mock.patch(
            "importer.tasks.items.requests.get",
            return_value=type(self).FakeResponse(payload, "image/png"),
        ):
            saved = download_and_set_item_thumbnail(item, url)
        item.refresh_from_db()
        self.assertEqual(saved, item.thumbnail_image.name)
        self.assertTrue(saved.endswith(".png"))
        self.assertTrue(default_storage.exists(saved))
        with default_storage.open(saved, "rb") as fh:
            self.assertEqual(fh.read(), payload)

    def test_fallback_extension_via_pillow_sniff_when_guess_is_bin(self):
        item = create_item()
        payload = self.make_image_bytes(fmt="PNG")
        url = "https://example.com/noext"  # no extension to force sniff path
        with (
            mock.patch("importer.tasks.items._guess_extension", return_value=".bin"),
            mock.patch(
                "importer.tasks.items.requests.get",
                return_value=type(self).FakeResponse(payload, content_type=""),
            ),
        ):
            saved = download_and_set_item_thumbnail(item, url)
        item.refresh_from_db()
        self.assertEqual(saved, item.thumbnail_image.name)
        # Pillow sniff sees PNG, so .png via the mapping in the function
        self.assertTrue(saved.endswith(".png"))
        self.assertTrue(default_storage.exists(saved))

    def test_invalid_image_raises_value_error(self):
        item = create_item()
        bad_bytes = b"not-an-image"
        with mock.patch(
            "importer.tasks.items.requests.get",
            return_value=type(self).FakeResponse(bad_bytes, "application/octet-stream"),
        ):
            with self.assertRaises(ValueError):
                download_and_set_item_thumbnail(item, "https://example.com/notimg")
        item.refresh_from_db()
        self.assertFalse(bool(item.thumbnail_image))

    def test_requests_exception_propagates(self):
        item = create_item()
        with mock.patch(
            "importer.tasks.items.requests.get",
            side_effect=requests.RequestException("error"),
        ):
            with self.assertRaises(requests.RequestException):
                download_and_set_item_thumbnail(item, "https://example.com/error")

    def test_race_present_after_download_skips_final_save(self):
        """Simulate another writer saving the thumbnail mid-download."""
        item = create_item()

        def _concurrent_writer():
            # Another process writes a thumbnail before the second transaction.
            item.refresh_from_db()
            item.thumbnail_image.save("pre.jpg", ContentFile(b"pre"), save=True)

        payload = self.make_image_bytes(fmt="PNG")
        with mock.patch(
            "importer.tasks.items.requests.get",
            return_value=type(self).FakeResponse(
                payload, "image/png", on_iter=_concurrent_writer
            ),
        ):
            msg = download_and_set_item_thumbnail(item, "https://example.com/new.png")
        self.assertIn("skipping save", msg.lower())
        item.refresh_from_db()
        self.assertTrue(item.thumbnail_image.name.endswith("pre.jpg"))
        self.assertTrue(default_storage.exists(item.thumbnail_image.name))

    def test_force_overwrite_path_runs_and_sets_thumbnail(self):
        item = create_item()
        # Seed an existing thumbnail
        item.thumbnail_image.save("existing.jpg", ContentFile(b"old"), save=True)
        payload = self.make_image_bytes(fmt="PNG")
        with mock.patch(
            "importer.tasks.items.requests.get",
            return_value=type(self).FakeResponse(payload, "image/png"),
        ):
            saved = download_and_set_item_thumbnail(
                item, "https://example.com/new.png", force=True
            )
        item.refresh_from_db()
        self.assertEqual(saved, item.thumbnail_image.name)
        self.assertTrue(saved.endswith(".png"))
        self.assertTrue(default_storage.exists(saved))

    def test_iter_content_skips_empty_chunks(self):
        """Ensure empty chunks are skipped and valid data is still written."""
        item = create_item()
        payload = self.make_image_bytes(fmt="PNG")

        class EmptyThenDataResponse:
            def __init__(self, data):
                self.headers = {"Content-Type": "image/png"}
                self._data = data

            def __enter__(self):  # context manager support
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def raise_for_status(self):
                return

            def iter_content(self, chunk_size=64 * 1024):
                # First an empty/falsy chunk, then the real PNG bytes.
                yield b""
                yield self._data

        with mock.patch(
            "importer.tasks.items.requests.get",
            return_value=EmptyThenDataResponse(payload),
        ):
            saved = download_and_set_item_thumbnail(
                item, "https://example.com/empty-first.png"
            )

        self.assertTrue(saved.endswith(".png"))
        self.assertTrue(default_storage.exists(saved))
        with default_storage.open(saved, "rb") as fh:
            self.assertEqual(fh.read(), payload)

    def test_uses_url_extension_when_no_content_type_and_ext_present(self):
        # No content-type, so fall back to URL; returns lowercase extension.
        ext = _guess_extension(None, "/path/to/IMAGE.JPG")
        self.assertEqual(ext, ".jpg")

    def test_returns_bin_when_no_content_type_and_no_url_extension(self):
        # No content-type and no extension in URL, so return ".bin"
        ext = _guess_extension(None, "/path/to/filename")
        self.assertEqual(ext, ".bin")

    @mock.patch("importer.tasks.items.mimetypes.guess_extension", return_value=None)
    def test_falls_back_to_url_when_content_type_unmapped(self, _mock_guess):
        # Content-Type is present but unmapped, meaning mimetypes.guess_extension
        # returns None, so the function must fall back to the URL and lowercase the
        # extension.
        ext = _guess_extension("application/x-unknown-type", "/some/Path/IMAGE.JPG")
        self.assertEqual(ext, ".jpg")
