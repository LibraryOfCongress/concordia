import io
import shutil
import tempfile
from unittest import mock

import requests
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from PIL import Image

from concordia.models import Item
from concordia.tests.utils import (
    CreateTestUsers,
    create_asset,
    create_item,
    create_project,
)
from importer import tasks
from importer.models import ImportItem
from importer.tasks.items import (
    download_and_set_item_thumbnail,
    get_item_id_from_item_url,
    get_item_info_from_result,
    import_items_into_project_from_url,
)
from importer.tests.utils import (
    create_import_item,
    create_import_job,
)


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
            tasks.items.import_item_count_from_url(None),
            ("None - Asset Count: 0", 0),
        )

    def test_unhandled_exception_importing(self):
        with mock.patch("importer.tasks.items.requests.get") as get_mock:
            get_mock.side_effect = AttributeError("Error message")
            self.assertEqual(
                tasks.items.import_item_count_from_url("http://example.com"),
                (
                    "Unhandled exception importing http://example.com " "Error message",
                    0,
                ),
            )


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
        # Ensure at least one asset exists for the item
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
                    f"Not reprocessing existing item with all assets: {item}"
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

    def test_create_item_import_task_full_clean_exception_updates_status_and_reraises(
        self, get_mock
    ):
        get_mock.return_value = self.response_mock
        self.response_mock.json.return_value = self.item_data

        with (
            self.assertLogs("importer.tasks", level="ERROR") as log,
            mock.patch("importer.tasks.items.Item.full_clean") as full_clean_mock,
            mock.patch("importer.tasks.items.import_item_task.delay") as task_mock,
            mock.patch(
                "importer.tasks.items.download_and_set_item_thumbnail"
            ) as thumb_mock,
        ):
            full_clean_mock.side_effect = RuntimeError("boom")
            with self.assertRaises(RuntimeError):
                tasks.items.create_item_import_task(self.job.pk, self.item_url)

            self.assertTrue(
                any("Unhandled exception when importing item" in m for m in log.output)
            )
            thumb_mock.assert_not_called()
            task_mock.assert_not_called()

        item = Item.objects.get(item_id=self.item_id)
        import_item = ImportItem.objects.get(item=item)
        self.assertIsNotNone(import_item.failed)
        self.assertIn("Unhandled exception: boom", import_item.status)

    def test_create_item_import_task_save_exception_updates_status_and_reraises(
        self, get_mock
    ):
        get_mock.return_value = self.response_mock
        self.response_mock.json.return_value = self.item_data

        # Grab the real save before patching so we can wrap it.
        from importer.tasks.items import Item as _Item

        real_save = _Item.save
        call_count = {"n": 0}

        def save_side_effect(self, *args, **kwargs):
            call_count["n"] += 1
            # First call is from Item.objects.get_or_create(...) -> allow it to
            # persist.
            if call_count["n"] == 1:
                return real_save(self, *args, **kwargs)
            # Second call is the one under test -> raise.
            raise RuntimeError("save failed")

        with (
            self.assertLogs("importer.tasks", level="ERROR") as log,
            mock.patch("importer.tasks.items.Item.full_clean") as full_clean_mock,
            mock.patch(
                "importer.tasks.items.Item.save",
                side_effect=save_side_effect,
                autospec=True,
            ),
            mock.patch("importer.tasks.items.import_item_task.delay") as task_mock,
            mock.patch(
                "importer.tasks.items.download_and_set_item_thumbnail"
            ) as thumb_mock,
        ):
            # Ensure full_clean does not fail so we reach save().
            full_clean_mock.return_value = None

            with self.assertRaises(RuntimeError):
                tasks.items.create_item_import_task(self.job.pk, self.item_url)

            self.assertTrue(
                any("Unhandled exception when importing item" in m for m in log.output)
            )
            thumb_mock.assert_not_called()
            task_mock.assert_not_called()

        item = Item.objects.get(item_id=self.item_id)
        import_item = ImportItem.objects.get(item=item)
        self.assertIsNotNone(import_item.failed)
        self.assertIn("Unhandled exception: save failed", import_item.status)


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
