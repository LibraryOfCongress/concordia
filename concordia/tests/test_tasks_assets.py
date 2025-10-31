from unittest import mock
from unittest.mock import PropertyMock

from django.test import TestCase

from concordia.models import Asset, TranscriptionStatus
from concordia.tasks.assets import (
    calculate_difficulty_values,
    fix_storage_images,
    populate_asset_years,
)

from .utils import (
    CreateTestUsers,
    create_asset,
    create_campaign,
    create_item,
    create_project,
    create_transcription,
)


class CalculateDifficultyValuesTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.user1 = self.create_test_user("cdv-user-1")
        self.user2 = self.create_test_user("cdv-user-2")
        self.reviewer = self.create_test_user("cdv-reviewer")
        self.campaign = create_campaign(slug="cdv-c")
        self.project = create_project(campaign=self.campaign, slug="cdv-p")
        self.item = create_item(project=self.project, item_id="cdv-i")

    def test_no_changes_when_difficulty_matches(self):
        asset = create_asset(item=self.item, slug="cdv-a1")
        # Default difficulty is zero and there are no transcriptions
        updated = calculate_difficulty_values(Asset.objects.filter(pk=asset.pk))
        self.assertEqual(updated, 0)
        asset.refresh_from_db()
        self.assertEqual(asset.difficulty, 0)

    def test_updates_difficulty_for_explicit_queryset(self):
        asset = create_asset(item=self.item, slug="cdv-a2")
        with mock.patch(
            "concordia.signals.handlers.calculate_difficulty_values", return_value=None
        ):
            # Two transcriptions by two users and one reviewer
            create_transcription(asset=asset, user=self.user1)
            create_transcription(
                asset=asset, user=self.user2, reviewed_by=self.reviewer
            )

        updated = calculate_difficulty_values(Asset.objects.filter(pk=asset.pk))
        self.assertEqual(updated, 1)

        asset.refresh_from_db()
        # transcription_count is 2; transcriber_count is 2; reviewer_count is 1
        # difficulty is 2 * (2 + 1), so difficulty should be 6
        self.assertEqual(asset.difficulty, 6)

    def test_default_published_queryset_and_chunking(self):
        # Build 501 published assets so we traverse more than one chunk
        first = None
        last = None
        for i in range(1, 502):
            a = create_asset(
                item=self.item,
                slug=f"cdv-bulk-{i}",
                sequence=i,
            )
            if i == 1:
                first = a
            if i == 501:
                last = a

        with mock.patch(
            "concordia.signals.handlers.calculate_difficulty_values", return_value=None
        ):
            # Add one transcription to first and last to force two updates
            create_transcription(asset=first, user=self.user1)
            create_transcription(asset=last, user=self.user1)
        updated = calculate_difficulty_values()
        self.assertEqual(updated, 2)

        first.refresh_from_db()
        last.refresh_from_db()
        self.assertEqual(first.difficulty, 1)
        self.assertEqual(last.difficulty, 1)


class PopulateAssetYearsTests(TestCase):
    def setUp(self):
        self.campaign = create_campaign(slug="pay-c")
        self.project = create_project(campaign=self.campaign, slug="pay-p")

        self.item1 = create_item(project=self.project, item_id="pay-i1")
        self.asset1 = create_asset(item=self.item1, slug="pay-a1")

        self.item2 = create_item(project=self.project, item_id="pay-i2")
        self.asset2 = create_asset(item=self.item2, slug="pay-a2")

        # Ensure both assets have the metadata shape the task expects and that
        # their current year matches that metadata so we can control which rows
        # update in individual tests without KeyErrors or unintended updates.
        self._set_metadata_dates(self.asset1, "2000")
        self._set_metadata_dates(self.asset2, "2000")
        Asset.objects.filter(pk__in=[self.asset1.pk, self.asset2.pk]).update(
            year="2000"
        )

    def _set_metadata_dates(self, asset, *years):
        # Populate minimal metadata structure expected by the task
        asset.item.metadata = {
            "item": {"dates": [{y: {}} for y in years]},
        }
        asset.item.save(update_fields=["metadata"])

    def test_updates_year_from_last_date_key(self):
        # Change asset1’s metadata so it needs an update; asset2 stays matched.
        self._set_metadata_dates(self.asset1, "1900", "1901")
        # Current year differs (2000), so an update should occur for asset1.
        updated = populate_asset_years()
        self.assertGreaterEqual(updated, 1)

        self.asset1.refresh_from_db()
        self.assertEqual(self.asset1.year, "1901")

    def test_skips_when_year_unchanged(self):
        # Keep asset1 year equal to its extracted year; asset2 is already matched
        self._set_metadata_dates(self.asset1, "1900")
        Asset.objects.filter(pk=self.asset1.pk).update(year="1900")

        updated = populate_asset_years()
        self.assertEqual(updated, 0)

    def test_multiple_assets_count_returned(self):
        # Both assets should change
        self._set_metadata_dates(self.asset1, "1910")
        self._set_metadata_dates(self.asset2, "1920")

        Asset.objects.filter(pk=self.asset1.pk).update(year="1900")
        Asset.objects.filter(pk=self.asset2.pk).update(year="1900")

        updated = populate_asset_years()
        self.assertEqual(updated, 2)

        self.asset1.refresh_from_db()
        self.asset2.refresh_from_db()
        self.assertEqual(self.asset1.year, "1910")
        self.assertEqual(self.asset2.year, "1920")

    def test_skips_empty_date_dicts_and_uses_last_year(self):
        # Use truly empty dicts ({}) so the inner loop over keys is not entered for
        # those entries; the task should still pick the last non-empty year.
        self.asset1.item.metadata = {
            "item": {"dates": [{}, {"1955": {}}, {}, {"1957": {}}]}
        }
        self.asset1.item.save(update_fields=["metadata"])

        # Ensure an update is needed.
        Asset.objects.filter(pk=self.asset1.pk).update(year="2000")

        updated = populate_asset_years()
        self.assertEqual(updated, 1)

        self.asset1.refresh_from_db()
        self.assertEqual(self.asset1.year, "1957")


class FixStorageImagesTests(TestCase):
    def setUp(self):
        self.campaign1 = create_campaign(slug="fsi-c1")
        self.project1 = create_project(campaign=self.campaign1, slug="fsi-p1")
        self.item1 = create_item(project=self.project1, item_id="fsi-i1")

        self.campaign2 = create_campaign(slug="fsi-c2")
        self.project2 = create_project(campaign=self.campaign2, slug="fsi-p2")
        self.item2 = create_item(project=self.project2, item_id="fsi-i2")

        self.asset1 = create_asset(
            item=self.item1,
            slug="fsi-a1",
            sequence=1,
            transcription_status=TranscriptionStatus.NOT_STARTED,
        )
        self.asset2 = create_asset(
            item=self.item1,
            slug="fsi-a2",
            sequence=2,
            transcription_status=TranscriptionStatus.IN_PROGRESS,
        )
        self.asset3 = create_asset(
            item=self.item2,
            slug="fsi-a3",
            sequence=3,
            transcription_status=TranscriptionStatus.SUBMITTED,
        )

    def test_skips_when_storage_image_exists(self):
        with (
            mock.patch(
                "django.core.files.storage.FileSystemStorage.exists",
                return_value=True,
            ),
            mock.patch("concordia.tasks.assets.requests.get") as mock_get,
            mock.patch("concordia.tasks.assets.ASSET_STORAGE.save") as mock_save,
        ):
            fix_storage_images()
            mock_get.assert_not_called()
            mock_save.assert_not_called()

    def test_downloads_and_saves_when_missing_success(self):
        expected_filename = "/".join(
            [
                self.campaign1.slug,
                self.project1.slug,
                self.item1.item_id,
                f"{self.asset1.sequence}.jpg",
            ]
        )

        with (
            mock.patch(
                "django.core.files.storage.FileSystemStorage.exists",
                return_value=False,
            ),
            mock.patch.object(
                Asset,
                "download_url",
                new_callable=PropertyMock,
                return_value="https://example.invalid/img.jpg",
            ),
            mock.patch("concordia.tasks.assets.requests.get") as mock_get,
            mock.patch("concordia.tasks.assets.ASSET_STORAGE.save") as mock_save,
        ):
            fake_response = mock.MagicMock()
            fake_response.iter_content.return_value = [b"abc", b"def"]
            fake_response.raise_for_status.return_value = None
            mock_get.return_value = fake_response

            fix_storage_images(campaign_slug=self.campaign1.slug)

            mock_get.assert_called()
            mock_save.assert_any_call(expected_filename, mock.ANY)

    def test_raises_and_logs_when_save_fails(self):
        with (
            mock.patch(
                "django.core.files.storage.FileSystemStorage.exists",
                return_value=False,
            ),
            mock.patch.object(
                Asset,
                "download_url",
                new_callable=PropertyMock,
                return_value="https://example.invalid/img.jpg",
            ),
            mock.patch("concordia.tasks.assets.requests.get") as mock_get,
            mock.patch(
                "concordia.tasks.assets.ASSET_STORAGE.save",
                side_effect=RuntimeError("save failed"),
            ),
            mock.patch("concordia.tasks.assets.logger") as mock_logger,
        ):
            fake_response = mock.MagicMock()
            fake_response.iter_content.return_value = [b"abc"]
            fake_response.raise_for_status.return_value = None
            mock_get.return_value = fake_response

            with self.assertRaises(RuntimeError):
                fix_storage_images(campaign_slug=self.campaign1.slug)

            self.assertTrue(mock_logger.exception.called)

    def test_filters_by_campaign_and_asset_start_id(self):
        with (
            mock.patch(
                "django.core.files.storage.FileSystemStorage.exists",
                return_value=False,
            ),
            mock.patch.object(
                Asset,
                "download_url",
                new_callable=PropertyMock,
                return_value="https://example.invalid/img.jpg",
            ),
            mock.patch("concordia.tasks.assets.requests.get") as mock_get,
            mock.patch("concordia.tasks.assets.ASSET_STORAGE.save") as mock_save,
        ):
            fake_response = mock.MagicMock()
            fake_response.iter_content.return_value = [b"x"]
            fake_response.raise_for_status.return_value = None
            mock_get.return_value = fake_response

            fix_storage_images(
                campaign_slug=self.campaign1.slug,
                asset_start_id=self.asset2.id,
            )

            self.assertEqual(mock_save.call_count, 1)
            expected_filename = "/".join(
                [
                    self.campaign1.slug,
                    self.project1.slug,
                    self.item1.item_id,
                    f"{self.asset2.sequence}.jpg",
                ]
            )
            mock_save.assert_called_with(expected_filename, mock.ANY)

    def test_skips_when_storage_image_is_falsy(self):
        # Make both campaign1 assets have a falsy storage_image, to
        # ensure we handle that case sanely
        Asset.objects.filter(pk__in=[self.asset1.pk, self.asset2.pk]).update(
            storage_image=""
        )

        with (
            mock.patch(
                "django.core.files.storage.FileSystemStorage.exists",
                return_value=True,
            ) as mock_exists,
            mock.patch("concordia.tasks.assets.requests.get") as mock_get,
            mock.patch("concordia.tasks.assets.ASSET_STORAGE.save") as mock_save,
        ):
            fix_storage_images(campaign_slug=self.campaign1.slug)

            # Nothing should be fetched or saved when storage_image is falsy.
            mock_get.assert_not_called()
            mock_save.assert_not_called()
            # And we should never even check existence for these assets.
            mock_exists.assert_not_called()
