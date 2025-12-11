from datetime import timedelta
from unittest import mock

from django.core.cache import caches
from django.test import TestCase, override_settings
from django.utils import timezone

from concordia.models import Campaign, SiteReport, TranscriptionStatus
from concordia.tasks.visualizations import (
    populate_asset_status_visualization_cache,
    populate_daily_activity_visualization_cache,
)

from .utils import create_asset, create_campaign, create_item, create_project


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        },
        "visualization_cache": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        },
    }
)
class VisualizationCacheTasksTests(TestCase):
    class _UploadFailed(Exception):
        pass

    def setUp(self):
        self.cache = caches["visualization_cache"]
        self.cache.clear()

    def test_populate_asset_status_visualization_cache(self):
        c1 = create_campaign(status=Campaign.Status.ACTIVE, title="Alpha")
        c2 = create_campaign(status=Campaign.Status.ACTIVE, title="Beta")
        p1 = create_project(campaign=c1)
        i1 = create_item(project=p1)
        p2 = create_project(campaign=c2)
        i2 = create_item(project=p2)
        create_asset(item=i1, transcription_status=TranscriptionStatus.NOT_STARTED)
        create_asset(
            item=i2,
            slug="test-asset-2",
            transcription_status=TranscriptionStatus.IN_PROGRESS,
        )
        create_asset(
            item=i2,
            slug="test-asset-3",
            transcription_status=TranscriptionStatus.SUBMITTED,
        )
        create_asset(
            item=i2,
            slug="test-asset-4",
            transcription_status=TranscriptionStatus.COMPLETED,
        )

        populate_asset_status_visualization_cache.run()

        overview = self.cache.get("asset-status-overview")
        expected_labels = [
            TranscriptionStatus.CHOICE_MAP[key]
            for key, _ in TranscriptionStatus.CHOICES
        ]
        self.assertEqual(overview["status_labels"], expected_labels)
        # Totals: 1 not_started, 1 in_progress, 1 submitted, 1 completed
        self.assertEqual(overview["total_counts"], [1, 1, 1, 1])

    def test_populate_daily_activity_visualization_cache(self):
        today = timezone.localdate()
        date1 = today - timedelta(days=2)
        date2 = today - timedelta(days=1)

        sr1 = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            transcriptions_saved=5,
            daily_review_actions=1,
        )
        sr2 = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            transcriptions_saved=10,
            daily_review_actions=2,
        )
        # Set specific created_on dates directly in DB
        SiteReport.objects.filter(pk=sr1.pk).update(created_on=date1)
        SiteReport.objects.filter(pk=sr2.pk).update(created_on=date2)

        populate_daily_activity_visualization_cache.run()

        result = self.cache.get("daily-transcription-activity-last-28-days")
        self.assertIsNotNone(result)

        expected_labels = [(date2 - timedelta(days=1)), date2]
        expected_labels = [d.strftime("%Y-%m-%d") for d in expected_labels]

        # Extract the two datasets
        datasets = result["transcription_datasets"]
        self.assertEqual(len(datasets), 2)
        trans = next(ds for ds in datasets if ds["label"] == "Transcriptions")
        reviews = next(ds for ds in datasets if ds["label"] == "Reviews")

        # transcriptions = 5 on date1, 10 - 5 = 5 on date2
        # reviews = 1 on date1, 2 on date2
        self.assertEqual(trans["data"][-2:], [5, 5])  # last two days in the data range
        self.assertEqual(reviews["data"][-2:], [1, 2])

    def test_negative_daily_saved_clamps_to_zero(self):
        today = timezone.localdate()
        date1 = today - timedelta(days=2)
        date2 = today - timedelta(days=1)

        sr1 = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            transcriptions_saved=10,
            daily_review_actions=0,
        )
        sr2 = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            transcriptions_saved=5,  # decreased total, which should not happen
            daily_review_actions=0,
        )
        SiteReport.objects.filter(pk=sr1.pk).update(created_on=date1)
        SiteReport.objects.filter(pk=sr2.pk).update(created_on=date2)

        populate_daily_activity_visualization_cache.run()

        result = self.cache.get("daily-transcription-activity-last-28-days")
        self.assertIsNotNone(result)

        datasets = result["transcription_datasets"]
        trans = next(ds for ds in datasets if ds["label"] == "Transcriptions")

        # Should clamp the second day to 0
        self.assertEqual(trans["data"][-2:], [10, 0])

    def test_asset_status_unchanged_skips_upload_and_cache_update(self):
        campaign = create_campaign(status=Campaign.Status.ACTIVE, title="Only")
        project = create_project(campaign=campaign)
        item = create_item(project=project)
        create_asset(item=item, transcription_status=TranscriptionStatus.NOT_STARTED)
        create_asset(
            item=item, slug="a2", transcription_status=TranscriptionStatus.IN_PROGRESS
        )
        create_asset(
            item=item, slug="a3", transcription_status=TranscriptionStatus.SUBMITTED
        )
        create_asset(
            item=item, slug="a4", transcription_status=TranscriptionStatus.COMPLETED
        )

        expected_counts = [1, 1, 1, 1]

        existing_payload = {
            "status_labels": [
                TranscriptionStatus.CHOICE_MAP[key]
                for key, _ in TranscriptionStatus.CHOICES
            ],
            "total_counts": expected_counts,
            "csv_url": "https://old.example/asset-status.csv",
        }
        self.cache.set("asset-status-overview", existing_payload, None)

        with (
            mock.patch(
                "concordia.tasks.visualizations.VISUALIZATION_STORAGE.save"
            ) as mock_save,
            mock.patch("concordia.tasks.visualizations.structured_logger") as mock_log,
        ):
            populate_asset_status_visualization_cache.run()

            mock_save.assert_not_called()
            # Cache should remain as-is
            self.assertEqual(self.cache.get("asset-status-overview"), existing_payload)
            # Logged unchanged
            self.assertTrue(mock_log.info.called)
            self.assertEqual(
                mock_log.info.call_args.kwargs.get("event_code"),
                "asset_status_vis_unchanged",
            )

    def test_asset_status_upload_failure_with_prior_url_falls_back(self):
        campaign = create_campaign(status=Campaign.Status.ACTIVE, title="Only")
        project = create_project(campaign=campaign)
        item = create_item(project=project)
        create_asset(item=item, transcription_status=TranscriptionStatus.NOT_STARTED)

        # Ensure "existing" differs so code takes the non-unchanged path
        self.cache.set(
            "asset-status-overview",
            {
                "status_labels": [],
                "total_counts": [0, 0, 0, 0],
                "csv_url": "https://old.example/asset-status.csv",
            },
            None,
        )

        with (
            mock.patch(
                "concordia.tasks.visualizations.VISUALIZATION_STORAGE.save",
                side_effect=self._UploadFailed("test exception"),
            ),
            mock.patch("concordia.tasks.visualizations.structured_logger") as mock_log,
        ):
            # Should not raise because we have a prior CSV URL to fall back to
            populate_asset_status_visualization_cache.run()

            updated = self.cache.get("asset-status-overview")
            # Counts should reflect the new data (1 in NOT_STARTED; others 0)
            expected = [
                1 if key == TranscriptionStatus.NOT_STARTED else 0
                for key, _ in TranscriptionStatus.CHOICES
            ]
            self.assertEqual(updated["total_counts"], expected)
            # URL should remain the old one
            self.assertEqual(updated["csv_url"], "https://old.example/asset-status.csv")

            # Logged exception with the non-missing-url code
            self.assertTrue(mock_log.exception.called)
            self.assertEqual(
                mock_log.exception.call_args.kwargs.get("event_code"),
                "asset_status_vis_csv_error",
            )

    def test_asset_status_upload_failure_without_prior_url_raises(self):
        campaign = create_campaign(status=Campaign.Status.ACTIVE, title="Only")
        project = create_project(campaign=campaign)
        item = create_item(project=project)
        create_asset(item=item, transcription_status=TranscriptionStatus.NOT_STARTED)

        # No existing cache entry, so no prior URL
        with (
            mock.patch(
                "concordia.tasks.visualizations.VISUALIZATION_STORAGE.save",
                side_effect=self._UploadFailed("test exception"),
            ),
            mock.patch("concordia.tasks.visualizations.structured_logger") as mock_log,
        ):
            with self.assertRaises(self._UploadFailed):
                populate_asset_status_visualization_cache.run()

            self.assertTrue(mock_log.exception.called)
            self.assertEqual(
                mock_log.exception.call_args.kwargs.get("event_code"),
                "asset_status_vis_csv_missing_url_error",
            )

    def test_daily_activity_unchanged_skips_upload_and_cache_update(self):
        # With no SiteReports, both series are 28 zeros; pre-populate matching cache
        zeros = [0] * 28
        existing = {
            "labels": [],  # labels do not matter for the dedupe
            "transcription_datasets": [
                {"label": "Transcriptions", "data": zeros},
                {"label": "Reviews", "data": zeros},
            ],
            "csv_url": "https://old.example/daily.csv",
        }
        self.cache.set("daily-transcription-activity-last-28-days", existing, None)

        with (
            mock.patch(
                "concordia.tasks.visualizations.VISUALIZATION_STORAGE.save"
            ) as mock_save,
            mock.patch("concordia.tasks.visualizations.structured_logger") as mock_log,
        ):
            populate_daily_activity_visualization_cache.run()

            mock_save.assert_not_called()
            self.assertEqual(
                self.cache.get("daily-transcription-activity-last-28-days"), existing
            )
            self.assertTrue(mock_log.info.called)
            self.assertEqual(
                mock_log.info.call_args.kwargs.get("event_code"),
                "daily_activity_vis_unchanged",
            )

    def test_daily_activity_upload_failure_with_prior_url_falls_back(self):
        # Build reports so new data will not be all zeros (ensures "changed" path)
        today = timezone.localdate()
        date1 = today - timedelta(days=2)
        date2 = today - timedelta(days=1)
        sr1 = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            transcriptions_saved=3,
            daily_review_actions=1,
        )
        sr2 = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            transcriptions_saved=5,
            daily_review_actions=2,
        )
        SiteReport.objects.filter(pk=sr1.pk).update(created_on=date1)
        SiteReport.objects.filter(pk=sr2.pk).update(created_on=date2)

        # Prior cache with different series and a CSV URL to fall back to
        self.cache.set(
            "daily-transcription-activity-last-28-days",
            {
                "labels": [],
                "transcription_datasets": [
                    {"label": "Transcriptions", "data": [0] * 28},
                    {"label": "Reviews", "data": [0] * 28},
                ],
                "csv_url": "https://old.example/daily.csv",
            },
            None,
        )

        with (
            mock.patch(
                "concordia.tasks.visualizations.VISUALIZATION_STORAGE.save",
                side_effect=self._UploadFailed("test exception"),
            ),
            mock.patch("concordia.tasks.visualizations.structured_logger") as mock_log,
        ):
            # Should not raise because we have a prior CSV URL
            populate_daily_activity_visualization_cache.run()

            updated = self.cache.get("daily-transcription-activity-last-28-days")
            self.assertIsNotNone(updated)
            # Still using the old URL
            self.assertEqual(updated["csv_url"], "https://old.example/daily.csv")
            # Logged exception with the non-missing-url code
            self.assertTrue(mock_log.exception.called)
            self.assertEqual(
                mock_log.exception.call_args.kwargs.get("event_code"),
                "daily_activity_vis_csv_error",
            )

    def test_daily_activity_upload_failure_without_prior_url_raises(self):
        # No existing cache entry -> csv_url is None
        with (
            mock.patch(
                "concordia.tasks.visualizations.VISUALIZATION_STORAGE.save",
                side_effect=self._UploadFailed("test exception"),
            ),
            mock.patch("concordia.tasks.visualizations.structured_logger") as mock_log,
        ):
            with self.assertRaises(self._UploadFailed):
                populate_daily_activity_visualization_cache.run()

            self.assertTrue(mock_log.exception.called)
            self.assertEqual(
                mock_log.exception.call_args.kwargs.get("event_code"),
                "daily_activity_vis_csv_missing_url_error",
            )
