from datetime import date, datetime
from types import SimpleNamespace
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from concordia.models import KeyMetricsReport, SiteReport
from concordia.tasks.reports.key_metrics import build_key_metrics_reports


class BuildKeyMetricsReportsTaskTests(TestCase):
    def _dt(self, days_ago):
        return timezone.now() - timezone.timedelta(days=days_ago)

    def test_recompute_all_calls_all_upserts(self):
        # Earliest SiteReport in the current month so only one month is walked.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(created_on=self._dt(2))

        # Seed one MONTHLY and one QUARTERLY row so the later stages run.
        today = timezone.localdate()
        fy = KeyMetricsReport.get_fiscal_year_for_date(today)
        fq = KeyMetricsReport.get_fiscal_quarter_for_date(today)

        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=today.replace(day=1),
            period_end=today,
            fiscal_year=fy,
            fiscal_quarter=fq,
            month=today.month,
        )
        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=today.replace(day=1),
            period_end=today,
            fiscal_year=fy,
            fiscal_quarter=fq,
        )

        with (
            mock.patch.object(KeyMetricsReport, "upsert_month") as up_m,
            mock.patch.object(KeyMetricsReport, "upsert_quarter") as up_q,
            mock.patch.object(KeyMetricsReport, "upsert_fiscal_year") as up_y,
        ):
            up_m.return_value = mock.Mock(period_start=None, period_end=None)
            up_q.return_value = mock.Mock(period_start=None, period_end=None)
            up_y.return_value = mock.Mock(period_start=None, period_end=None)

            changed = build_key_metrics_reports.run(recompute_all=True)

        # One month, four quarters, one fiscal year
        self.assertEqual(changed, 6)
        self.assertEqual(up_m.call_count, 1)
        self.assertEqual(up_q.call_count, 4)
        self.assertEqual(up_y.call_count, 1)

    def test_incremental_refresh_and_creates(self):
        # Make one SiteReport this month so the month is considered.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(created_on=self._dt(2))

        today = timezone.localdate()
        fy = KeyMetricsReport.get_fiscal_year_for_date(today)
        fq = KeyMetricsReport.get_fiscal_quarter_for_date(today)

        # Existing MONTHLY row with old updated_on so it is refreshed.
        monthly = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=today.replace(day=1),
            period_end=today,
            fiscal_year=fy,
            fiscal_quarter=fq,
            month=today.month,
        )
        KeyMetricsReport.objects.filter(pk=monthly.pk).update(updated_on=self._dt(5))

        # Existing QUARTERLY row for the same quarter with older updated_on,
        # so it should be refreshed. The other three quarters are missing and
        # will be created.
        quarter = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=today.replace(day=1),
            period_end=today,
            fiscal_year=fy,
            fiscal_quarter=fq,
        )
        KeyMetricsReport.objects.filter(pk=quarter.pk).update(updated_on=self._dt(5))

        # No FY row yet so it will be created in the FY stage.
        with (
            mock.patch.object(KeyMetricsReport, "upsert_month") as up_m,
            mock.patch.object(KeyMetricsReport, "upsert_quarter") as up_q,
            mock.patch.object(KeyMetricsReport, "upsert_fiscal_year") as up_y,
        ):
            up_m.return_value = mock.Mock(period_start=None, period_end=None)
            up_q.return_value = mock.Mock(period_start=None, period_end=None)
            up_y.return_value = mock.Mock(period_start=None, period_end=None)

            changed = build_key_metrics_reports.run(recompute_all=False)

        # One monthly refresh, three quarterly creates (no refresh since the mock
        # does not bump monthly.updated_on), and one fiscal year create.
        self.assertEqual(changed, 5)
        self.assertEqual(up_m.call_count, 1)
        self.assertEqual(up_q.call_count, 3)
        self.assertEqual(up_y.call_count, 1)

    @mock.patch("concordia.tasks.reports.key_metrics.structured_logger")
    @mock.patch("concordia.tasks.reports.key_metrics.SiteReport")
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_early_return_after_backsteps(self, mock_local, mock_sr, slog):
        # Force "today" to mid-March so last_month_start starts at Mar 1.
        mock_local.return_value = date(2024, 3, 15)

        # Earliest SR is mid-December so first_month_start is Dec 1.
        earliest = SimpleNamespace(
            created_on=timezone.make_aware(datetime(2023, 12, 15, 12, 0, 0))
        )
        mock_sr.objects.order_by.return_value.first.return_value = earliest

        # Pretend there are no snapshots by EOM for any month we check.
        mock_sr.objects.filter.return_value.exists.return_value = False

        changed = build_key_metrics_reports.run(recompute_all=False)
        self.assertEqual(changed, 0)

        # Ensure we logged the "no months" message.
        codes = [kw.get("event_code") for _, kw in slog.info.call_args_list if kw]
        self.assertIn("key_metrics_build_no_months", codes)

    @mock.patch("concordia.tasks.reports.key_metrics.structured_logger")
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_recompute_all_month_upsert_and_december_rollover(
        self, mock_local, upsert_month, slog
    ):
        # Make yesterday in December so the month we process is December.
        mock_local.return_value = date(2023, 12, 20)

        # Create a TOTAL snapshot in December so the scan does not early-return.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2023, 12, 15, 10, 0, 0))
        )

        # Return a stub report so the "upserted" logging runs.
        upsert_month.return_value = SimpleNamespace(
            period_start=date(2023, 12, 1),
            period_end=date(2023, 12, 31),
        )

        changed = build_key_metrics_reports.run(recompute_all=True)
        self.assertGreaterEqual(changed, 1)

        codes = [kw.get("event_code") for _, kw in slog.info.call_args_list if kw]
        self.assertIn("key_metrics_month_upserted", codes)

    @mock.patch("concordia.tasks.reports.key_metrics.structured_logger")
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_fiscal_year"
    )
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_incremental_month_create_and_refresh(
        self,
        mock_local,
        upsert_month,
        upsert_year,
        upsert_quarter,
        slog,
    ):
        mock_local.return_value = date(2024, 2, 1)

        sr_jan = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr_jan.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 10, 9, 0, 0))
        )
        sr_dec = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr_dec.pk).update(
            created_on=timezone.make_aware(datetime(2023, 12, 20, 9, 0, 0))
        )

        dec_month = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=date(2023, 12, 1),
            period_end=date(2023, 12, 31),
            fiscal_year=2024,
            fiscal_quarter=1,
            month=12,
        )
        KeyMetricsReport.objects.filter(pk=dec_month.pk).update(
            updated_on=timezone.make_aware(datetime(2023, 12, 1, 0, 0, 0))
        )

        # Monthly upsert produces a stub (so it counts as 1 change per call)
        upsert_month.return_value = SimpleNamespace(
            period_start=date(2024, 1, 1), period_end=date(2024, 1, 31)
        )
        # Disable quarterly and fiscal-year increments
        upsert_quarter.return_value = None
        upsert_year.return_value = None

        changed = build_key_metrics_reports.run(recompute_all=False)
        self.assertEqual(changed, 2)

    @mock.patch("concordia.tasks.reports.key_metrics.structured_logger")
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.objects")
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_quarter_recompute_all_logs(
        self, mock_local, upsert_month, upsert_quarter, kmr_objects, slog
    ):
        mock_local.return_value = date(2024, 1, 15)

        # Ensure we do not early-return (one SR anywhere is fine).
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 1, 8, 0, 0))
        )

        # We are not using monthly upserts here.
        upsert_month.return_value = None

        # monthly_rows -> one fiscal year (2024)
        kmr_objects.filter.return_value.values.return_value.annotate.return_value = [
            {"fiscal_year": 2024}
        ]
        # quarter_exists .first() can be anything; ignored in recompute_all.
        kmr_objects.filter.return_value.first.return_value = None
        # Prevent FY stage from running by returning no quarter years later.
        kmr_objects.filter.return_value.values_list.return_value = []

        upsert_quarter.return_value = SimpleNamespace(
            period_start=date(2024, 1, 1), period_end=date(2024, 3, 31)
        )

        changed = build_key_metrics_reports.run(recompute_all=True)
        # Four quarters upserted
        self.assertGreaterEqual(changed, 4)
        self.assertEqual(upsert_quarter.call_count, 4)

        codes = [kw.get("event_code") for _, kw in slog.info.call_args_list if kw]
        self.assertIn("key_metrics_quarter_upserted", codes)

    @mock.patch("concordia.tasks.reports.key_metrics.structured_logger")
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.objects")
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_quarter_incremental_refresh_all_quarters(
        self, mock_local, upsert_month, kmr_objects, upsert_quarter, slog
    ):
        mock_local.return_value = date(2024, 6, 15)

        # Ensure we do not early-return.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 5, 10, 8, 0, 0))
        )

        # No monthly creation in this test.
        upsert_month.return_value = None

        # Signal that we have monthly rows for fiscal_year=2024.
        kmr_objects.filter.return_value.values.return_value.annotate.return_value = [
            {"fiscal_year": 2024}
        ]

        # quarter_exists present for all four quarters.
        quarter_stub = SimpleNamespace(
            updated_on=timezone.make_aware(datetime(2024, 1, 1, 0, 0, 0))
        )

        def filter_side_effect(*args, **kwargs):
            # For QUARTERLY lookups with fiscal_quarter, return an object
            # whose first() yields a stub so "refresh" path is taken.
            class QS:
                def __init__(self, exists_value=False):
                    self._exists = exists_value

                def first(self):
                    return quarter_stub

                def exists(self):
                    return self._exists

                def values(self, *a, **k):
                    return self

                def annotate(self, *a, **k):
                    return [{"fiscal_year": 2024}]

                def values_list(self, *a, **k):
                    # Avoid FY stage in this test
                    return []

            pt = kwargs.get("period_type")
            if pt == KeyMetricsReport.PeriodType.MONTHLY and "updated_on__gt" in kwargs:
                # Make monthly_newer_exists True
                return QS(exists_value=True)
            return QS()

        kmr_objects.filter.side_effect = filter_side_effect

        upsert_quarter.return_value = SimpleNamespace(
            period_start=date(2024, 4, 1), period_end=date(2024, 6, 30)
        )

        changed = build_key_metrics_reports.run(recompute_all=False)
        # Four refreshes (Q1..Q4)
        self.assertGreaterEqual(changed, 4)
        self.assertEqual(upsert_quarter.call_count, 4)

        codes = [kw.get("event_code") for _, kw in slog.info.call_args_list if kw]
        self.assertIn("key_metrics_quarter_refreshed", codes)

    @mock.patch("concordia.tasks.reports.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_fiscal_year"
    )
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.objects")
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_fiscal_year_recompute_all_logs(
        self, mock_local, upsert_month, kmr_objects, upsert_year, slog
    ):
        mock_local.return_value = date(2024, 1, 15)

        # Ensure no early-return.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 2, 8, 0, 0))
        )

        upsert_month.return_value = None

        # No monthlies needed; quarters present for FY 2027.
        kmr_objects.filter.return_value.values.return_value.annotate.return_value = []
        kmr_objects.filter.return_value.values_list.return_value = [2027]
        kmr_objects.filter.return_value.first.return_value = None

        upsert_year.return_value = SimpleNamespace(
            period_start=date(2026, 10, 1), period_end=date(2027, 9, 30)
        )

        changed = build_key_metrics_reports.run(recompute_all=True)
        self.assertGreaterEqual(changed, 1)

        codes = [kw.get("event_code") for _, kw in slog.info.call_args_list if kw]
        self.assertIn("key_metrics_year_upserted", codes)

    @mock.patch("concordia.tasks.reports.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_fiscal_year"
    )
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.objects")
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_fiscal_year_incremental_create_and_refresh(
        self, mock_local, upsert_month, kmr_objects, upsert_year, slog
    ):
        mock_local.return_value = date(2024, 5, 1)

        # Ensure no early-return.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 4, 15, 8, 0, 0))
        )
        upsert_month.return_value = None

        # First, drive "create" path: quarters exist, FY row is missing.
        def filter_values_list_side_effect(*args, **kwargs):
            # This handles the "fiscal_years_with_quarters" query.
            class QS:
                def values_list(self, *a, **k):
                    return [2026]

                def first(self):
                    return None

                def values(self, *a, **k):
                    return self

                def annotate(self, *a, **k):
                    return []

                def exists(self):
                    return False

            return QS()

        kmr_objects.filter.side_effect = filter_values_list_side_effect

        upsert_year.return_value = SimpleNamespace(
            period_start=date(2025, 10, 1), period_end=date(2026, 9, 30)
        )

        changed1 = build_key_metrics_reports.run(recompute_all=False)
        self.assertGreaterEqual(changed1, 1)
        codes1 = [kw.get("event_code") for _, kw in slog.info.call_args_list if kw]
        self.assertIn("key_metrics_year_created", codes1)

        # Now drive "refresh" path: FY exists, a newer quarter exists.
        fy_stub = SimpleNamespace(
            updated_on=timezone.make_aware(datetime(2024, 3, 1, 0, 0, 0))
        )

        def filter_refresh_side_effect(*args, **kwargs):
            class QS:
                def __init__(self, pt=None):
                    self.pt = pt

                def values_list(self, *a, **k):
                    return [2026]

                def first(self):
                    # When asking for the FY row, return a stub
                    return fy_stub

                def values(self, *a, **k):
                    return self

                def annotate(self, *a, **k):
                    return []

                def exists(self):
                    # This is called for quarters newer than FY.updated_on
                    return True

            return QS()

        kmr_objects.filter.side_effect = filter_refresh_side_effect

        upsert_year.return_value = SimpleNamespace(
            period_start=date(2025, 10, 1), period_end=date(2026, 9, 30)
        )

        changed2 = build_key_metrics_reports.run(recompute_all=False)
        self.assertGreaterEqual(changed2, 1)
        codes2 = [kw.get("event_code") for _, kw in slog.info.call_args_list if kw]
        self.assertIn("key_metrics_year_refreshed", codes2)

    @mock.patch("concordia.tasks.reports.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_fiscal_year"
    )
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_recompute_all_quarter_upserts_only(
        self, mock_local, mock_month, mock_quarter, mock_year, slog
    ):
        mock_local.return_value = date(2024, 2, 1)

        # Seed one site snapshot so the task has a start month (Jan 2024).
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 10, 9, 0, 0))
        )

        # Seed a MONTHLY row so the quarter loop sees FY 2024 in the set.
        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
            month=1,
        )

        # Monthly does nothing; quarter upserts return a stub; FY does nothing.
        mock_month.return_value = None
        mock_year.return_value = None

        def quarter_stub(**kwargs):
            return SimpleNamespace(
                period_start=date(2024, 1, 1), period_end=date(2024, 3, 31)
            )

        mock_quarter.side_effect = quarter_stub

        changed = build_key_metrics_reports.run(recompute_all=True)

        # Only quarters (4) should have counted.
        self.assertEqual(changed, 4)
        self.assertEqual(mock_quarter.call_count, 4)

    @mock.patch("concordia.tasks.reports.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_fiscal_year"
    )
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_incremental_quarter_refresh_only(
        self, mock_local, mock_month, mock_quarter, mock_year, slog
    ):
        mock_local.return_value = date(2024, 4, 1)

        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 10, 9, 0, 0))
        )

        # Monthlies for Q2; newer than the quarter row we will refresh
        for m in (1, 2, 3):
            mr = KeyMetricsReport.objects.create(
                period_type=KeyMetricsReport.PeriodType.MONTHLY,
                period_start=date(2024, m, 1),
                period_end=KeyMetricsReport.month_bounds(date(2024, m, 15))[1],
                fiscal_year=2024,
                fiscal_quarter=2,
                month=m,
            )
            KeyMetricsReport.objects.filter(pk=mr.pk).update(
                updated_on=timezone.make_aware(datetime(2024, 3, 31, 12, 0, 0))
            )

        # Pre-create Q1, Q3, Q4 so they are not created by the task
        for fq, ps, pe in [
            (1, date(2023, 10, 1), date(2023, 12, 31)),
            (3, date(2024, 4, 1), date(2024, 6, 30)),
            (4, date(2024, 7, 1), date(2024, 9, 30)),
        ]:
            KeyMetricsReport.objects.create(
                period_type=KeyMetricsReport.PeriodType.QUARTERLY,
                period_start=ps,
                period_end=pe,
                fiscal_year=2024,
                fiscal_quarter=fq,
            )

        # Existing Q2 with older updated_on so only this quarter refreshes
        q2 = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )
        KeyMetricsReport.objects.filter(pk=q2.pk).update(
            updated_on=timezone.make_aware(datetime(2024, 1, 15, 0, 0, 0))
        )

        mock_month.return_value = None
        mock_year.return_value = None
        mock_quarter.return_value = SimpleNamespace(
            period_start=date(2024, 1, 1), period_end=date(2024, 3, 31)
        )

        changed = build_key_metrics_reports.run(recompute_all=False)

        self.assertEqual(changed, 1)
        self.assertEqual(mock_quarter.call_count, 1)

    @mock.patch("concordia.tasks.reports.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_fiscal_year"
    )
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_recompute_all_year_upsert_only(
        self, mock_local, mock_month, mock_quarter, mock_year, slog
    ):
        mock_local.return_value = date(2024, 2, 1)

        # Seed snapshot to allow the task to pick a month.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 10, 9, 0, 0))
        )

        # Ensure the 'fiscal_years_with_quarters' set is not empty.
        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )

        # Monthly and quarterly stages do nothing; FY upsert returns a stub.
        mock_month.return_value = None
        mock_quarter.return_value = None
        mock_year.return_value = SimpleNamespace(
            period_start=date(2024, 10, 1), period_end=date(2025, 9, 30)
        )

        changed = build_key_metrics_reports.run(recompute_all=True)

        self.assertEqual(changed, 1)
        self.assertEqual(mock_year.call_count, 1)

    @mock.patch("concordia.tasks.reports.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_fiscal_year"
    )
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_incremental_year_create(
        self, mock_local, mock_month, mock_quarter, mock_year, slog
    ):
        mock_local.return_value = date(2024, 2, 1)

        # Seed snapshot and a quarterly row so year loop triggers.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 10, 9, 0, 0))
        )
        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )

        mock_month.return_value = None
        mock_quarter.return_value = None
        mock_year.return_value = SimpleNamespace(
            period_start=date(2024, 10, 1), period_end=date(2025, 9, 30)
        )

        changed = build_key_metrics_reports.run(recompute_all=False)

        self.assertEqual(changed, 1)
        self.assertEqual(mock_year.call_count, 1)

    @mock.patch("concordia.tasks.reports.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_fiscal_year"
    )
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_incremental_year_refresh(
        self, mock_local, mock_month, mock_quarter, mock_year, slog
    ):
        mock_local.return_value = date(2024, 4, 1)

        # Seed a quarterly row with new updated_on.
        q = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )
        KeyMetricsReport.objects.filter(pk=q.pk).update(
            updated_on=timezone.make_aware(datetime(2024, 3, 31, 12, 0, 0))
        )

        # Create an older FY row that should be refreshed.
        fy = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.FISCAL_YEAR,
            period_start=date(2023, 10, 1),
            period_end=date(2024, 9, 30),
            fiscal_year=2024,
        )
        KeyMetricsReport.objects.filter(pk=fy.pk).update(
            updated_on=timezone.make_aware(datetime(2024, 1, 1, 0, 0, 0))
        )

        # Need a snapshot so the task can initialize months; it is not used
        # further because we neutralize month and quarter stages.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 10, 9, 0, 0))
        )

        mock_month.return_value = None
        mock_quarter.return_value = None
        mock_year.return_value = SimpleNamespace(
            period_start=date(2023, 10, 1), period_end=date(2024, 9, 30)
        )

        changed = build_key_metrics_reports.run(recompute_all=False)

        self.assertEqual(changed, 1)
        self.assertEqual(mock_year.call_count, 1)

    @mock.patch("concordia.tasks.reports.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_fiscal_year"
    )
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_quarter_recompute_all_upserts_and_continue(
        self,
        mock_localdate,
        mock_upsert_month,
        mock_upsert_quarter,
        mock_upsert_year,
        slog,
    ):
        # Make the "monthly" section inert (no changes).
        mock_localdate.return_value = date(2024, 4, 1)
        mock_upsert_month.return_value = None
        mock_upsert_year.return_value = None

        # Seed minimal SiteReport so the monthly stage can compute bounds safely.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 10, 9, 0, 0))
        )

        # Ensure at least one fiscal_year is discovered from MONTHLY rows.
        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
            month=1,
        )

        # Each quarter upsert returns a non-None object so rows_changed increments.
        mock_upsert_quarter.return_value = SimpleNamespace(
            period_start=date(2024, 1, 1), period_end=date(2024, 3, 31)
        )

        changed = build_key_metrics_reports.run(recompute_all=True)

        # Four quarters upserted; monthly and FY upserts return None.
        self.assertEqual(changed, 4)
        self.assertEqual(mock_upsert_quarter.call_count, 4)

    @mock.patch("concordia.tasks.reports.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_fiscal_year"
    )
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_fiscal_year_recompute_all_upserts_and_continue(
        self,
        mock_localdate,
        mock_upsert_month,
        mock_upsert_quarter,
        mock_upsert_year,
        slog,
    ):
        mock_localdate.return_value = date(2024, 4, 1)
        mock_upsert_month.return_value = None
        mock_upsert_quarter.return_value = None

        # Seed a quarter so the FY stage finds a fiscal year to process.
        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )

        # Earliest SiteReport so earlier stages do not error.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 5, 9, 0, 0))
        )

        mock_upsert_year.return_value = SimpleNamespace(
            period_start=date(2023, 10, 1), period_end=date(2024, 9, 30)
        )

        changed = build_key_metrics_reports.run(recompute_all=True)

        # Only FY upsert counts (quarter/month upserts return None).
        self.assertEqual(changed, 1)
        self.assertEqual(mock_upsert_year.call_count, 1)

    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_month",
        return_value=None,
    )
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_quarter_recompute_all_non_none_continue_edge(
        self, mock_localdate, mock_upsert_quarter, mock_upsert_month
    ):
        mock_localdate.return_value = date(2024, 5, 20)

        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 5, 10, 12, 0, 0))
        )

        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=date(2024, 5, 1),
            period_end=date(2024, 5, 31),
            fiscal_year=2024,
            fiscal_quarter=3,
            month=5,
        )

        dummy = mock.MagicMock(
            period_start=date(2024, 1, 1), period_end=date(2024, 3, 31)
        )
        mock_upsert_quarter.return_value = dummy

        changed = build_key_metrics_reports(recompute_all=True)

        self.assertEqual(changed, 4)
        self.assertEqual(mock_upsert_quarter.call_count, 4)

    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_month",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_quarter",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_fiscal_year",
        return_value=mock.MagicMock(
            period_start=date(2024, 10, 1), period_end=date(2025, 9, 30)
        ),
    )
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_quarter_incremental_refresh_monthly_newer(
        self,
        mock_localdate,
        mock_upsert_fy,
        mock_upsert_quarter,
        mock_upsert_month,
    ):
        mock_localdate.return_value = date(2024, 1, 20)

        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 10, 9, 0, 0))
        )

        jan = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
            month=1,
        )
        KeyMetricsReport.objects.filter(pk=jan.pk).update(updated_on=timezone.now())

        now = timezone.now()
        older = now - timezone.timedelta(days=10)
        q1 = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2023, 10, 1),
            period_end=date(2023, 12, 31),
            fiscal_year=2024,
            fiscal_quarter=1,
        )
        q2 = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )
        q3 = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 4, 1),
            period_end=date(2024, 6, 30),
            fiscal_year=2024,
            fiscal_quarter=3,
        )
        q4 = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 7, 1),
            period_end=date(2024, 9, 30),
            fiscal_year=2024,
            fiscal_quarter=4,
        )
        KeyMetricsReport.objects.filter(pk=q1.pk).update(updated_on=now)
        KeyMetricsReport.objects.filter(pk=q2.pk).update(updated_on=older)
        KeyMetricsReport.objects.filter(pk=q3.pk).update(updated_on=now)
        KeyMetricsReport.objects.filter(pk=q4.pk).update(updated_on=now)

        fy = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.FISCAL_YEAR,
            period_start=date(2023, 10, 1),
            period_end=date(2024, 9, 30),
            fiscal_year=2024,
        )
        KeyMetricsReport.objects.filter(pk=fy.pk).update(updated_on=now)

        mock_upsert_quarter.return_value = mock.MagicMock(
            period_start=date(2024, 1, 1), period_end=date(2024, 3, 31)
        )

        changed = build_key_metrics_reports.run(recompute_all=False)

        self.assertEqual(changed, 1)
        self.assertGreaterEqual(mock_upsert_quarter.call_count, 1)

    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_month",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_quarter",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_fiscal_year",
        return_value=mock.MagicMock(
            period_start=date(2024, 10, 1), period_end=date(2025, 9, 30)
        ),
    )
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_fiscal_year_recompute_all_non_none_continue_edge(
        self, mock_localdate, mock_upsert_fy, mock_upsert_quarter, mock_upsert_month
    ):
        mock_localdate.return_value = date(2024, 5, 20)

        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 5, 10, 12, 0, 0))
        )

        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )

        changed = build_key_metrics_reports(recompute_all=True)
        self.assertEqual(changed, 1)

    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_month",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_quarter",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_fiscal_year",
        return_value=mock.MagicMock(
            period_start=date(2024, 10, 1), period_end=date(2025, 9, 30)
        ),
    )
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_fiscal_year_incremental_create_missing(
        self,
        mock_localdate,
        mock_upsert_fy,
        mock_upsert_quarter,
        mock_upsert_month,
    ):
        mock_localdate.return_value = date(2024, 5, 20)

        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        tz = timezone.get_current_timezone()
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 5, 10, 12, 0, 0), tz)
        )

        for qn, start, end in [
            (1, date(2023, 10, 1), date(2023, 12, 31)),
            (2, date(2024, 1, 1), date(2024, 3, 31)),
            (3, date(2024, 4, 1), date(2024, 6, 30)),
            (4, date(2024, 7, 1), date(2024, 9, 30)),
        ]:
            KeyMetricsReport.objects.create(
                period_type=KeyMetricsReport.PeriodType.QUARTERLY,
                period_start=start,
                period_end=end,
                fiscal_year=2024,
                fiscal_quarter=qn,
            )

        changed = build_key_metrics_reports(recompute_all=False)
        self.assertEqual(changed, 1)

    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_month",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_quarter",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_fiscal_year",
        return_value=mock.MagicMock(
            period_start=date(2024, 10, 1), period_end=date(2025, 9, 30)
        ),
    )
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_fiscal_year_incremental_refresh_when_quarter_newer(
        self, mock_localdate, mock_upsert_fy, mock_upsert_quarter, mock_upsert_month
    ):
        mock_localdate.return_value = date(2024, 5, 20)

        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 5, 10, 12, 0, 0))
        )

        older = timezone.now() - timezone.timedelta(days=7)
        newer = timezone.now()

        fy = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.FISCAL_YEAR,
            period_start=date(2023, 10, 1),
            period_end=date(2024, 9, 30),
            fiscal_year=2024,
        )
        KeyMetricsReport.objects.filter(pk=fy.pk).update(updated_on=older)

        q2 = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )
        KeyMetricsReport.objects.filter(pk=q2.pk).update(updated_on=newer)

        changed = build_key_metrics_reports(recompute_all=False)
        self.assertEqual(changed, 1)

    @mock.patch("concordia.tasks.reports.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_fiscal_year",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_month",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_quarter",
        return_value=None,
    )
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_quarter_recompute_all_none_branch_continue(
        self, mock_localdate, upsert_quarter, upsert_month, upsert_year, slog
    ):
        # Keep the monthly scan minimal and stable
        mock_localdate.return_value = date(2024, 2, 10)

        # Seed a site snapshot so the task computes month bounds
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(
                datetime(2024, 2, 9, 12, 0, 0), timezone.get_current_timezone()
            )
        )

        # Ensure the quarterly stage iterates a fiscal year by having a MONTHLY row
        fy = KeyMetricsReport.get_fiscal_year_for_date(mock_localdate.return_value)
        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=date(2024, 2, 1),
            period_end=date(2024, 2, 29),
            fiscal_year=fy,
            fiscal_quarter=2,
            month=2,
        )

        # upsert_quarter returns None -> branch falls through to 'continue'
        changed = build_key_metrics_reports.run(recompute_all=True)

        # No rows changed because monthly and FY are neutralized and quarter
        # upserts return None (hitting the continue path each time).
        self.assertEqual(changed, 0)
        self.assertEqual(upsert_quarter.call_count, 4)

    @mock.patch("concordia.tasks.reports.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_fiscal_year",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_month",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_quarter",
        return_value=None,
    )
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_quarter_incremental_refresh_none_branch_continue(
        self,
        mock_localdate,
        mock_upsert_quarter,
        mock_upsert_month,
        mock_upsert_year,
        slog,
    ):
        # Ensure monthly scan has a valid window
        mock_localdate.return_value = date(2024, 2, 10)

        # Seed one site snapshot so month range can be computed
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        tz = timezone.get_current_timezone()
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 5, 12, 0, 0), tz)
        )

        # Provide a MONTHLY row in FY 2024; make it "newer" than Q2
        jan = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
            month=1,
        )
        KeyMetricsReport.objects.filter(pk=jan.pk).update(updated_on=timezone.now())

        # Create quarter rows so the incremental branch runs.
        # Only Q2 should be older than the monthly row to trigger refresh.
        now = timezone.now()
        older = now - timezone.timedelta(days=10)
        quarters = {
            1: ((date(2023, 10, 1), date(2023, 12, 31)), now),
            2: ((date(2024, 1, 1), date(2024, 3, 31)), older),
            3: ((date(2024, 4, 1), date(2024, 6, 30)), now),
            4: ((date(2024, 7, 1), date(2024, 9, 30)), now),
        }
        for fq, val in quarters.items():
            (ps, pe), updated = val
            q = KeyMetricsReport.objects.create(
                period_type=KeyMetricsReport.PeriodType.QUARTERLY,
                period_start=ps,
                period_end=pe,
                fiscal_year=2024,
                fiscal_quarter=fq,
            )
            KeyMetricsReport.objects.filter(pk=q.pk).update(updated_on=updated)

        # upsert_quarter is mocked to return None, so when the code reaches the
        # monthly_newer_exists refresh path for Q2 it will take the "is None"
        # branch and continue without incrementing rows_changed.
        changed = build_key_metrics_reports.run(recompute_all=False)

        # No rows changed: month and year upserts return None, and Q2 refresh
        # returned None (so branch continued). Only one refresh attempt expected.
        self.assertEqual(changed, 0)
        self.assertEqual(mock_upsert_quarter.call_count, 1)

    @mock.patch("concordia.tasks.reports.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_fiscal_year",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_quarter",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_month",
        return_value=None,
    )
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_fiscal_year_recompute_all_none_branch_continue(
        self,
        mock_localdate,
        mock_upsert_month,
        mock_upsert_quarter,
        mock_upsert_year,
        slog,
    ):
        mock_localdate.return_value = date(2024, 5, 20)

        # Ensure monthly scan can initialize.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        tz = timezone.get_current_timezone()
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 5, 10, 12, 0, 0), tz)
        )

        # Ensure at least one fiscal year is present for the FY stage.
        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )

        # Month/quarter upserts are mocked to None; FY upsert also None.
        changed = build_key_metrics_reports.run(recompute_all=True)

        # Nothing should be counted since FY upsert returned None and the code
        # immediately continued the loop without incrementing or logging.
        self.assertEqual(changed, 0)
        self.assertEqual(mock_upsert_year.call_count, 1)

        codes = [kw.get("event_code") for _, kw in slog.info.call_args_list if kw]
        self.assertNotIn("key_metrics_year_upserted", codes)

    @mock.patch("concordia.tasks.reports.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_fiscal_year",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_quarter",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_month",
        return_value=None,
    )
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_fiscal_year_incremental_refresh_none_branch_continue(
        self,
        mock_localdate,
        mock_upsert_month,
        mock_upsert_quarter,
        mock_upsert_year,
        slog,
    ):
        mock_localdate.return_value = date(2024, 5, 20)

        # Make monthly stage computable.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        tz = timezone.get_current_timezone()
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 5, 10, 12, 0, 0), tz)
        )

        # Existing FY row with older updated_on so a newer quarter will
        # trigger the refresh path.
        fy = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.FISCAL_YEAR,
            period_start=date(2023, 10, 1),
            period_end=date(2024, 9, 30),
            fiscal_year=2024,
        )
        KeyMetricsReport.objects.filter(pk=fy.pk).update(
            updated_on=timezone.make_aware(datetime(2024, 3, 1, 0, 0, 0), tz)
        )

        # Quarter newer than the FY row to make quarter_newer_exists True.
        q2 = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )
        KeyMetricsReport.objects.filter(pk=q2.pk).update(
            updated_on=timezone.make_aware(datetime(2024, 3, 15, 0, 0, 0), tz)
        )

        # FY upsert returns None so the branch is skipped and loop continues.
        changed = build_key_metrics_reports.run(recompute_all=False)

        self.assertEqual(changed, 0)
        self.assertEqual(mock_upsert_year.call_count, 1)

        codes = [kw.get("event_code") for _, kw in slog.info.call_args_list if kw]
        self.assertNotIn("key_metrics_year_refreshed", codes)
        self.assertNotIn("key_metrics_year_created", codes)
        self.assertNotIn("key_metrics_year_upserted", codes)

    @mock.patch("concordia.tasks.reports.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_fiscal_year"
    )
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_incremental_fiscal_year_created_branch(
        self,
        mock_localdate,
        mock_upsert_month,
        mock_upsert_quarter,
        mock_upsert_year,
        slog,
    ):
        mock_localdate.return_value = date(2024, 4, 1)
        mock_upsert_month.return_value = None
        mock_upsert_quarter.return_value = None

        # Quarter exists for FY discovery; no FY row exists yet.
        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )

        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 2, 9, 0, 0))
        )

        mock_upsert_year.return_value = SimpleNamespace(
            period_start=date(2023, 10, 1), period_end=date(2024, 9, 30)
        )

        changed = build_key_metrics_reports.run(recompute_all=False)

        self.assertEqual(changed, 1)
        self.assertEqual(mock_upsert_year.call_count, 1)

    @mock.patch("concordia.tasks.reports.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_fiscal_year"
    )
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch("concordia.tasks.reports.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.reports.key_metrics.timezone.localdate")
    def test_incremental_fiscal_year_refresh_due_to_newer_quarter(
        self,
        mock_localdate,
        mock_upsert_month,
        mock_upsert_quarter,
        mock_upsert_year,
        slog,
    ):
        mock_localdate.return_value = date(2024, 4, 1)
        mock_upsert_month.return_value = None
        mock_upsert_quarter.return_value = None

        # Existing FY row with earlier updated_on.
        fy = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.FISCAL_YEAR,
            period_start=date(2023, 10, 1),
            period_end=date(2024, 9, 30),
            fiscal_year=2024,
        )
        KeyMetricsReport.objects.filter(pk=fy.pk).update(
            updated_on=timezone.make_aware(datetime(2024, 3, 1, 0, 0, 0))
        )

        # Quarter with newer updated_on to trigger the refresh path.
        q = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )
        KeyMetricsReport.objects.filter(pk=q.pk).update(
            updated_on=timezone.make_aware(datetime(2024, 3, 15, 0, 0, 0))
        )

        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 3, 9, 0, 0))
        )

        mock_upsert_year.return_value = SimpleNamespace(
            period_start=date(2023, 10, 1), period_end=date(2024, 9, 30)
        )

        changed = build_key_metrics_reports.run(recompute_all=False)

        self.assertEqual(changed, 1)
        self.assertEqual(mock_upsert_year.call_count, 1)
