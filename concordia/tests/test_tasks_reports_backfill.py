from django.test import TestCase
from django.utils import timezone

from concordia.models import Campaign, SiteReport, Topic
from concordia.tasks.reports.backfill import (
    backfill_assets_started_for_site_reports,
)


class BackfillAssetsStartedTaskTests(TestCase):
    def _dt(self, days_ago):
        return timezone.now() - timezone.timedelta(days=days_ago)

    def test_updates_total_and_skips_existing_by_default(self):
        # Three TOTAL rows in time order. The last is already populated and
        # should be skipped in default mode.
        r1 = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            assets_total=100,
            assets_not_started=100,
            assets_published=10,
            assets_started=None,
        )
        r2 = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            assets_total=107,
            assets_not_started=92,
            assets_published=17,
            assets_started=None,
        )
        r3 = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            assets_total=100,
            assets_not_started=90,
            assets_published=20,
            assets_started=5,
        )

        dt1 = self._dt(3)
        dt2 = self._dt(2)
        dt3 = self._dt(1)

        SiteReport.objects.filter(pk=r1.pk).update(created_on=dt1)
        SiteReport.objects.filter(pk=r2.pk).update(created_on=dt2)
        SiteReport.objects.filter(pk=r3.pk).update(created_on=dt3)

        # The TOTAL series assets_started is now expected to be rolled up from
        # per-campaign series that were generated on the same reporting day.
        camp1 = Campaign.objects.create(title="C1", slug="c1")
        camp2 = Campaign.objects.create(title="C2", slug="c2")

        c1_prev = SiteReport.objects.create(
            campaign=camp1,
            assets_total=50,
            assets_not_started=50,
            assets_published=0,
            assets_started=None,
        )
        c1_curr = SiteReport.objects.create(
            campaign=camp1,
            assets_total=50,
            assets_not_started=40,
            assets_published=0,
            assets_started=None,
        )

        c2_prev = SiteReport.objects.create(
            campaign=camp2,
            assets_total=50,
            assets_not_started=50,
            assets_published=0,
            assets_started=None,
        )
        c2_curr = SiteReport.objects.create(
            campaign=camp2,
            assets_total=52,
            assets_not_started=47,
            assets_published=0,
            assets_started=None,
        )

        SiteReport.objects.filter(pk=c1_prev.pk).update(created_on=dt1)
        SiteReport.objects.filter(pk=c1_curr.pk).update(created_on=dt2)
        SiteReport.objects.filter(pk=c2_prev.pk).update(created_on=dt1)
        SiteReport.objects.filter(pk=c2_curr.pk).update(created_on=dt2)

        updated = backfill_assets_started_for_site_reports.run()
        # Campaign series (2 campaigns x 2 rows) + TOTAL series (2 rows).
        self.assertEqual(updated, 6)

        r1.refresh_from_db()
        r2.refresh_from_db()
        r3.refresh_from_db()
        c1_prev.refresh_from_db()
        c1_curr.refresh_from_db()
        c2_prev.refresh_from_db()
        c2_curr.refresh_from_db()

        self.assertEqual(c1_prev.assets_started, 0)
        self.assertEqual(c1_curr.assets_started, 10)
        self.assertEqual(c2_prev.assets_started, 0)
        self.assertEqual(c2_curr.assets_started, 5)

        self.assertEqual(r1.assets_started, 0)
        self.assertEqual(r2.assets_started, 15)
        self.assertEqual(r3.assets_started, 5)

    def test_recompute_when_skip_existing_is_false(self):
        # Build a TOTAL series with two rows. Make the first row have a wrong,
        # non-null assets_started so it should be recomputed when
        # skip_existing is False.
        #
        # The TOTAL series assets_started is expected to be rolled up from
        # per-campaign series generated on the same reporting day.
        now = timezone.now()

        prev = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            assets_total=100,
            assets_not_started=100,
            assets_published=10,
        )
        curr = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            assets_total=105,
            assets_not_started=90,
            assets_published=15,
        )

        dt_prev = now - timezone.timedelta(days=2)
        dt_curr = now - timezone.timedelta(days=1)

        # Enforce chronological order for the iterator
        SiteReport.objects.filter(pk=prev.pk).update(created_on=dt_prev)
        SiteReport.objects.filter(pk=curr.pk).update(created_on=dt_curr)

        # Wrong non-null on first row, null on second.
        SiteReport.objects.filter(pk=prev.pk).update(assets_started=5)
        SiteReport.objects.filter(pk=curr.pk).update(assets_started=None)

        camp = Campaign.objects.create(title="C", slug="c")

        c_prev = SiteReport.objects.create(
            campaign=camp,
            assets_total=100,
            assets_not_started=100,
            assets_published=0,
            assets_started=None,
        )
        c_curr = SiteReport.objects.create(
            campaign=camp,
            assets_total=105,
            assets_not_started=90,
            assets_published=0,
            assets_started=None,
        )
        SiteReport.objects.filter(pk=c_prev.pk).update(created_on=dt_prev)
        SiteReport.objects.filter(pk=c_curr.pk).update(created_on=dt_curr)

        updated = backfill_assets_started_for_site_reports.run(skip_existing=False)
        # Campaign series (2 rows) + TOTAL series (2 rows).
        self.assertEqual(updated, 4)

        prev_refreshed = SiteReport.objects.get(pk=prev.pk)
        curr_refreshed = SiteReport.objects.get(pk=curr.pk)
        c_prev.refresh_from_db()
        c_curr.refresh_from_db()

        self.assertEqual(c_prev.assets_started, 0)
        self.assertEqual(c_curr.assets_started, 15)

        self.assertEqual(prev_refreshed.assets_started, 0)
        self.assertEqual(curr_refreshed.assets_started, 15)

    def test_processes_retired_campaign_and_topic_series(self):
        # One RETIRED_TOTAL row
        rt = SiteReport.objects.create(
            report_name=SiteReport.ReportName.RETIRED_TOTAL,
            assets_not_started=10,
            assets_published=2,
            assets_started=None,
        )
        SiteReport.objects.filter(pk=rt.pk).update(created_on=self._dt(3))

        # One per-campaign row
        camp = Campaign.objects.create(title="C", slug="c")
        cr = SiteReport.objects.create(
            campaign=camp,
            assets_not_started=7,
            assets_published=1,
            assets_started=None,
        )
        SiteReport.objects.filter(pk=cr.pk).update(created_on=self._dt(2))

        # One per-topic row
        topic = Topic.objects.create(title="T", slug="t")
        tr = SiteReport.objects.create(
            topic=topic,
            assets_not_started=5,
            assets_published=0,
            assets_started=None,
        )
        SiteReport.objects.filter(pk=tr.pk).update(created_on=self._dt(1))

        updated = backfill_assets_started_for_site_reports.run()
        # Each single-row series sets assets_started to 0
        self.assertEqual(updated, 3)

        rt.refresh_from_db()
        cr.refresh_from_db()
        tr.refresh_from_db()
        self.assertEqual(rt.assets_started, 0)
        self.assertEqual(cr.assets_started, 0)
        self.assertEqual(tr.assets_started, 0)

    def test_skip_existing_branch_emits_heartbeat_due_to_time(self):
        # First row already populated (skipped); second row needs update.
        from unittest import mock

        prev = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            assets_not_started=100,
            assets_published=10,
            assets_started=0,
        )
        curr = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            assets_not_started=90,
            assets_published=15,
            assets_started=None,
        )

        SiteReport.objects.filter(pk=prev.pk).update(created_on=self._dt(2))
        SiteReport.objects.filter(pk=curr.pk).update(created_on=self._dt(1))

        # Use a monotonic function that always advances time enough to trip the
        # heartbeat-by-time condition, without exhausting side effects.
        def make_monotonic(step=11.0):
            state = {"t": 0.0}

            def _mono():
                state["t"] += step
                return state["t"]

            return _mono

        with (
            mock.patch("concordia.tasks.reports.backfill.structured_logger") as slog,
            mock.patch(
                "concordia.tasks.reports.backfill.time.monotonic",
                new=make_monotonic(),
            ),
        ):
            updated = backfill_assets_started_for_site_reports.run()
            self.assertEqual(updated, 1)

            hb_calls = [
                c
                for c in slog.info.call_args_list
                if c.kwargs.get("event_code")
                == "assets_started_backfill_series_heartbeat"
                and c.kwargs.get("series") == "TOTAL"
                and c.kwargs.get("scanned_rows") == 1
                and c.kwargs.get("last_seen_site_report_id") == prev.id
            ]
            self.assertTrue(hb_calls)

    def test_post_scan_heartbeat_emitted_due_to_time(self):
        # Single-row series where a save occurs, then a heartbeat fires due to
        # elapsed time.
        from unittest import mock

        single = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            assets_not_started=50,
            assets_published=5,
            assets_started=None,
        )
        SiteReport.objects.filter(pk=single.pk).update(created_on=self._dt(1))

        def make_monotonic(step=11.0):
            state = {"t": 0.0}

            def _mono():
                state["t"] += step
                return state["t"]

            return _mono

        with (
            mock.patch("concordia.tasks.reports.backfill.structured_logger") as slog,
            mock.patch(
                "concordia.tasks.reports.backfill.time.monotonic",
                new=make_monotonic(),
            ),
        ):
            updated = backfill_assets_started_for_site_reports.run()
            self.assertEqual(updated, 1)

            slog.info.assert_any_call(
                "Scanning series...",
                event_code="assets_started_backfill_series_heartbeat",
                series="TOTAL",
                scanned_rows=1,
                updated_rows=1,
                last_seen_site_report_id=single.id,
            )

    def test_no_update_when_equal_with_skip_existing_false(self):
        # First row already equals the calculated value (zero for first snapshot),
        # so no save should occur on that row when recomputing.
        from unittest import mock

        prev = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            assets_not_started=100,
            assets_published=10,
            assets_started=0,
        )
        curr = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            assets_not_started=90,
            assets_published=15,
            assets_started=None,
        )

        SiteReport.objects.filter(pk=prev.pk).update(created_on=self._dt(2))
        SiteReport.objects.filter(pk=curr.pk).update(created_on=self._dt(1))

        with mock.patch("concordia.tasks.reports.backfill.structured_logger") as slog:
            updated = backfill_assets_started_for_site_reports.run(skip_existing=False)
            self.assertEqual(updated, 1)

            # Row logs should not include the first row, since it already matched.
            row_logs = [
                c.kwargs
                for c in slog.info.call_args_list
                if c.kwargs.get("event_code") == "assets_started_backfill_row"
            ]
            self.assertTrue(any(kw.get("site_report_id") == curr.id for kw in row_logs))
            self.assertFalse(
                any(kw.get("site_report_id") == prev.id for kw in row_logs)
            )

    def test_total_assets_started_is_rolled_up_from_campaign_series(self):
        # Ensure the TOTAL series does not derive assets_started from its own
        # assets_total/assets_not_started deltas when campaign series data for
        # the same reporting days exists.
        camp = Campaign.objects.create(title="C", slug="c")

        total_prev = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            assets_total=999,
            assets_not_started=999,
            assets_started=None,
        )
        total_curr = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            assets_total=999,
            assets_not_started=0,
            assets_started=None,
        )

        c_prev = SiteReport.objects.create(
            campaign=camp,
            assets_total=20,
            assets_not_started=20,
            assets_started=None,
        )
        c_curr = SiteReport.objects.create(
            campaign=camp,
            assets_total=20,
            assets_not_started=15,
            assets_started=None,
        )

        dt_prev = self._dt(2)
        dt_curr = self._dt(1)

        SiteReport.objects.filter(pk=total_prev.pk).update(created_on=dt_prev)
        SiteReport.objects.filter(pk=total_curr.pk).update(created_on=dt_curr)
        SiteReport.objects.filter(pk=c_prev.pk).update(created_on=dt_prev)
        SiteReport.objects.filter(pk=c_curr.pk).update(created_on=dt_curr)

        updated = backfill_assets_started_for_site_reports.run(skip_existing=False)
        self.assertEqual(updated, 4)

        total_prev.refresh_from_db()
        total_curr.refresh_from_db()
        c_prev.refresh_from_db()
        c_curr.refresh_from_db()

        self.assertEqual(c_prev.assets_started, 0)
        self.assertEqual(c_curr.assets_started, 5)

        self.assertEqual(total_prev.assets_started, 0)
        self.assertEqual(total_curr.assets_started, 5)
