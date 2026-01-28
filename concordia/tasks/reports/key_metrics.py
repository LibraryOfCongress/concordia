import datetime
from logging import getLogger

from django.db.models import Max
from django.utils import timezone

from concordia.decorators import locked_task
from concordia.logging import ConcordiaLogger
from concordia.models import KeyMetricsReport, SiteReport

from ...celery import app as celery_app

logger = getLogger(__name__)
structured_logger = ConcordiaLogger.get_logger(__name__)


@celery_app.task(bind=True, ignore_result=True)
@locked_task(lock_by_args=False)
def build_key_metrics_reports(self, recompute_all: bool = False) -> int:
    """
    Build or refresh KeyMetricsReport rows (monthly, quarterly and fiscal year).

    The task operates in two modes, controlled by ``recompute_all``:

    - If ``recompute_all`` is True:
        - Recompute every monthly period that can be derived from
          SiteReport data.
        - Recompute all quarters that have at least one monthly row.
        - Recompute all fiscal years that have at least one quarterly
          row.
    - If ``recompute_all`` is False (incremental mode):
        - Create any missing monthly rows.
        - Refresh a monthly row if any SiteReport in that month has
          ``created_on`` later than the row's ``updated_on`` value.
        - Create any missing quarter rows that have at least one
          monthly row.
        - Refresh a quarter row if any of its monthly inputs have
          ``updated_on`` later than the quarter's ``updated_on`` value.
        - Create any missing fiscal year rows that have at least one
          quarter row.
        - Refresh a fiscal year row if any of its quarterly inputs have
          ``updated_on`` later than the fiscal year's ``updated_on``
          value.

    Args:
        recompute_all: If True, recompute all monthly, quarterly and
            fiscal-year rows from scratch based on SiteReport data. If
            False, only create missing rows and refresh rows that are
            stale.

    Returns:
        int: Count of KeyMetricsReport rows created or updated.
    """
    task_id = getattr(self.request, "id", None)
    structured_logger.info(
        "Starting KeyMetricsReport build.",
        event_code="key_metrics_build_start",
        task_id=task_id,
        recompute_all=recompute_all,
    )

    rows_changed = 0

    # Determine month range we can evaluate
    earliest_site_report = SiteReport.objects.order_by("created_on", "pk").first()
    earliest_date = earliest_site_report.created_on.date()
    first_month_start = earliest_date.replace(day=1)

    # Use local date for boundary logic
    today_local = timezone.localdate()
    # Evaluate up to the month containing "yesterday"
    # so we never rely on future EOM snapshots
    yesterday_local = today_local - datetime.timedelta(days=1)
    _, latest_evaluated_end_of_month = KeyMetricsReport.month_bounds(yesterday_local)

    def has_any_snapshot_by_end_of_month(month_start: datetime.date) -> bool:
        _, end_of_month = KeyMetricsReport.month_bounds(month_start)
        return SiteReport.objects.filter(created_on__date__lte=end_of_month).exists()

    last_month_start = latest_evaluated_end_of_month.replace(day=1)
    # Step back if the very latest month has no SiteReport by its EOM
    while (
        last_month_start >= first_month_start
        and not has_any_snapshot_by_end_of_month(last_month_start)
    ):
        if last_month_start.month == 1:
            last_month_start = last_month_start.replace(
                year=last_month_start.year - 1, month=12, day=1
            )
        else:
            last_month_start = last_month_start.replace(
                month=last_month_start.month - 1, day=1
            )

    if last_month_start < first_month_start:
        structured_logger.info(
            "No computable monthly periods found.",
            event_code="key_metrics_build_no_months",
            task_id=task_id,
        )
        return 0

    # Monthly

    months_processed: list[datetime.date] = []
    current_month_start = first_month_start
    while current_month_start <= last_month_start:
        year = current_month_start.year
        month = current_month_start.month
        _, current_month_end = KeyMetricsReport.month_bounds(current_month_start)

        if recompute_all:
            report = KeyMetricsReport.upsert_month(year=year, month=month)
            if report is not None:
                rows_changed += 1
                months_processed.append(current_month_start)
                structured_logger.info(
                    "Upserted monthly KeyMetricsReport.",
                    event_code="key_metrics_month_upserted",
                    year=year,
                    month=month,
                    period_start=str(report.period_start),
                    period_end=str(report.period_end),
                    task_id=task_id,
                )
        else:
            # Incremental mode: create missing, or refresh if stale
            existing_monthly_report = KeyMetricsReport.objects.filter(
                period_type=KeyMetricsReport.PeriodType.MONTHLY,
                fiscal_year=KeyMetricsReport.get_fiscal_year_for_date(
                    current_month_start
                ),
                month=month,
            ).first()

            if existing_monthly_report is None:
                report = KeyMetricsReport.upsert_month(year=year, month=month)
                if report is not None:
                    rows_changed += 1
                    months_processed.append(current_month_start)
                    structured_logger.info(
                        "Created missing monthly KeyMetricsReport.",
                        event_code="key_metrics_month_created",
                        year=year,
                        month=month,
                        period_start=str(report.period_start),
                        period_end=str(report.period_end),
                        task_id=task_id,
                    )
            else:
                # Refresh if any SiteReport within this month (TOTAL
                # or RETIRED_TOTAL, site-wide) has been created after
                # the monthly report was last updated.
                site_report_newer_exists = SiteReport.objects.filter(
                    report_name__in=(
                        SiteReport.ReportName.TOTAL,
                        SiteReport.ReportName.RETIRED_TOTAL,
                    ),
                    campaign__isnull=True,
                    topic__isnull=True,
                    created_on__date__gte=current_month_start,
                    created_on__date__lte=current_month_end,
                    created_on__gt=existing_monthly_report.updated_on,
                ).exists()

                if site_report_newer_exists:
                    report = KeyMetricsReport.upsert_month(year=year, month=month)
                    if report is not None:
                        rows_changed += 1
                        months_processed.append(current_month_start)
                        structured_logger.info(
                            (
                                "Refreshed monthly KeyMetricsReport "
                                "due to newer SiteReports."
                            ),
                            event_code="key_metrics_month_refreshed",
                            year=year,
                            month=month,
                            period_start=str(report.period_start),
                            period_end=str(report.period_end),
                            task_id=task_id,
                        )

        # Next month
        if month == 12:
            current_month_start = current_month_start.replace(
                year=year + 1, month=1, day=1
            )
        else:
            current_month_start = current_month_start.replace(month=month + 1, day=1)

    # Quarterly

    # Ensure we know which quarters exist (or should exist) given MONTHLY rows
    monthly_rows = (
        KeyMetricsReport.objects.filter(period_type=KeyMetricsReport.PeriodType.MONTHLY)
        .values("fiscal_year")
        .annotate(max_month=Max("month"))
    )
    # We will iterate over all fiscal_years that have at least one monthly row
    fiscal_years_with_monthlies = {row["fiscal_year"] for row in monthly_rows}

    # Create missing quarters and refresh stale ones
    for fiscal_year in sorted(fiscal_years_with_monthlies):
        for fiscal_quarter in (1, 2, 3, 4):
            quarter_exists = KeyMetricsReport.objects.filter(
                period_type=KeyMetricsReport.PeriodType.QUARTERLY,
                fiscal_year=fiscal_year,
                fiscal_quarter=fiscal_quarter,
            ).first()

            if recompute_all:
                quarter_report = KeyMetricsReport.upsert_quarter(
                    fiscal_year=fiscal_year, fiscal_quarter=fiscal_quarter
                )
                if quarter_report is not None:
                    rows_changed += 1
                    structured_logger.info(
                        "Upserted quarterly KeyMetricsReport.",
                        event_code="key_metrics_quarter_upserted",
                        fiscal_year=fiscal_year,
                        fiscal_quarter=fiscal_quarter,
                        period_start=str(quarter_report.period_start),
                        period_end=str(quarter_report.period_end),
                        task_id=task_id,
                    )
                continue

            # Incremental mode
            if quarter_exists is None:
                quarter_report = KeyMetricsReport.upsert_quarter(
                    fiscal_year=fiscal_year, fiscal_quarter=fiscal_quarter
                )
                if quarter_report is not None:
                    rows_changed += 1
                    structured_logger.info(
                        "Created missing quarterly KeyMetricsReport.",
                        event_code="key_metrics_quarter_created",
                        fiscal_year=fiscal_year,
                        fiscal_quarter=fiscal_quarter,
                        period_start=str(quarter_report.period_start),
                        period_end=str(quarter_report.period_end),
                        task_id=task_id,
                    )
            else:
                # Refresh if any constituent MONTHLY rows are newer than the quarter row
                if fiscal_quarter == 1:
                    month_list = [10, 11, 12]
                    monthly_fiscal_year = fiscal_year
                elif fiscal_quarter == 2:
                    month_list = [1, 2, 3]
                    monthly_fiscal_year = fiscal_year
                elif fiscal_quarter == 3:
                    month_list = [4, 5, 6]
                    monthly_fiscal_year = fiscal_year
                else:
                    month_list = [7, 8, 9]
                    monthly_fiscal_year = fiscal_year

                monthly_newer_exists = KeyMetricsReport.objects.filter(
                    period_type=KeyMetricsReport.PeriodType.MONTHLY,
                    fiscal_year=monthly_fiscal_year,
                    month__in=month_list,
                    updated_on__gt=quarter_exists.updated_on,
                ).exists()

                if monthly_newer_exists:
                    quarter_report = KeyMetricsReport.upsert_quarter(
                        fiscal_year=fiscal_year, fiscal_quarter=fiscal_quarter
                    )
                    if quarter_report is not None:
                        rows_changed += 1
                        structured_logger.info(
                            (
                                "Refreshed quarterly KeyMetricsReport "
                                "due to newer monthly inputs."
                            ),
                            event_code="key_metrics_quarter_refreshed",
                            fiscal_year=fiscal_year,
                            fiscal_quarter=fiscal_quarter,
                            period_start=str(quarter_report.period_start),
                            period_end=str(quarter_report.period_end),
                            task_id=task_id,
                        )

    # Fiscal year

    # Any fiscal year that has at least one quarter row should have a FY rollup
    fiscal_years_with_quarters = set(
        KeyMetricsReport.objects.filter(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY
        ).values_list("fiscal_year", flat=True)
    )

    for fiscal_year in sorted(fiscal_years_with_quarters):
        fiscal_year_report = KeyMetricsReport.objects.filter(
            period_type=KeyMetricsReport.PeriodType.FISCAL_YEAR,
            fiscal_year=fiscal_year,
        ).first()

        if recompute_all:
            year_report = KeyMetricsReport.upsert_fiscal_year(fiscal_year=fiscal_year)
            if year_report is not None:
                rows_changed += 1
                structured_logger.info(
                    "Upserted fiscal-year KeyMetricsReport.",
                    event_code="key_metrics_year_upserted",
                    fiscal_year=fiscal_year,
                    period_start=str(year_report.period_start),
                    period_end=str(year_report.period_end),
                    task_id=task_id,
                )
            continue

        if fiscal_year_report is None:
            year_report = KeyMetricsReport.upsert_fiscal_year(fiscal_year=fiscal_year)
            if year_report is not None:
                rows_changed += 1
                structured_logger.info(
                    "Created missing fiscal-year KeyMetricsReport.",
                    event_code="key_metrics_year_created",
                    fiscal_year=fiscal_year,
                    period_start=str(year_report.period_start),
                    period_end=str(year_report.period_end),
                    task_id=task_id,
                )
        else:
            # Refresh if any constituent QUARTER rows are newer than the FY row
            quarter_newer_exists = KeyMetricsReport.objects.filter(
                period_type=KeyMetricsReport.PeriodType.QUARTERLY,
                fiscal_year=fiscal_year,
                updated_on__gt=fiscal_year_report.updated_on,
            ).exists()

            if quarter_newer_exists:
                year_report = KeyMetricsReport.upsert_fiscal_year(
                    fiscal_year=fiscal_year
                )
                if year_report is not None:
                    rows_changed += 1
                    structured_logger.info(
                        (
                            "Refreshed fiscal-year KeyMetricsReport "
                            "due to newer quarterly inputs."
                        ),
                        event_code="key_metrics_year_refreshed",
                        fiscal_year=fiscal_year,
                        period_start=str(year_report.period_start),
                        period_end=str(year_report.period_end),
                        task_id=task_id,
                    )

    structured_logger.info(
        "Completed KeyMetricsReport build.",
        event_code="key_metrics_build_complete",
        rows_changed=rows_changed,
        task_id=task_id,
        recompute_all=recompute_all,
    )
    return rows_changed
