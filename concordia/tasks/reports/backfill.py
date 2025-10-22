import time
from logging import getLogger
from typing import Iterable, Optional

from concordia.decorators import locked_task
from concordia.logging import ConcordiaLogger
from concordia.models import SiteReport

from ...celery import app as celery_app

logger = getLogger(__name__)
structured_logger = ConcordiaLogger.get_logger(__name__)


@celery_app.task(bind=True, ignore_result=True)
@locked_task(lock_by_args=False)
def backfill_assets_started_for_site_reports(self, skip_existing: bool = True) -> int:
    """
    Compute and persist `assets_started` for all existing SiteReport rows.

    This is a temporary job for backfilling missing information in SiteReports.
    It should be removed in the next release after it goes live and has been run.

    Series processed:
      - Site-wide TOTAL                (report_name=TOTAL)
      - Site-wide RETIRED_TOTAL        (report_name=RETIRED_TOTAL)
      - Per-campaign                   (campaign is not null)
      - Per-topic                      (topic is not null)

    Rules:
      - The first "snapshot" in each series assumes assets_started = 0 (this
        represents when the site launched or at least the time before the
        first site report, when we have no data).
      - If there are gaps in days, the previous value is simply the most
        recent prior report in that series.
      - All results are floored at 0, since negative numbers are not actually
        possible in reality--the cause would be data removal, which we do not
        want to treat as negative activity in these reports.

    Resumability:
      - By default, rows that already have a non-null `assets_started` are
        skipped (`skip_existing=True`), so the task can be re-run to resume
        where it left off.
      - If you need to recompute all rows (for example, after changing the
        formula), call with `skip_existing=False`.

    Progress visibility:
      - Emits heartbeat logs while scanning long series so it does not appear
        idle when no rows need updates.
    """

    structured_logger.info(
        "Starting backfill for assets_started across all series.",
        event_code="assets_started_backfill_start",
        skip_existing=skip_existing,
        task_id=getattr(self.request, "id", None),
    )

    # Heartbeat / streaming tuning
    HEARTBEAT_EVERY_ROWS = 1000
    HEARTBEAT_EVERY_SECONDS = 10.0
    ITERATOR_CHUNK_SIZE = 2000

    updated_count = 0

    def process_series_queryset(
        qs: Iterable[SiteReport],
        *,
        series_label: str,
    ) -> int:
        """
        Walk a single series in chronological order, computing/saving
        `assets_started`. Logs each saved row at info level with context,
        and emits heartbeat logs even when no rows change.
        """
        changed = 0
        scanned = 0
        previous: Optional[SiteReport] = None

        series_start_t = time.monotonic()
        last_hb_t = series_start_t
        last_hb_rows = 0

        structured_logger.info(
            "Starting series scan.",
            event_code="assets_started_backfill_series_start",
            series=series_label,
        )

        for current in qs.iterator(chunk_size=ITERATOR_CHUNK_SIZE):
            scanned += 1

            if previous is None:
                calculated = 0
            else:
                calculated = SiteReport.calculate_assets_started(
                    previous_assets_not_started=previous.assets_not_started,
                    previous_assets_published=previous.assets_published,
                    current_assets_not_started=current.assets_not_started,
                    current_assets_published=current.assets_published,
                )

            # Resume behavior: optionally skip already-populated rows.
            if skip_existing and current.assets_started is not None:
                previous = current
                # Heartbeat while scanning even if we do not save
                now_t = time.monotonic()
                if (
                    scanned - last_hb_rows >= HEARTBEAT_EVERY_ROWS
                    or (now_t - last_hb_t) >= HEARTBEAT_EVERY_SECONDS
                ):
                    structured_logger.info(
                        "Scanning series...",
                        event_code="assets_started_backfill_series_heartbeat",
                        series=series_label,
                        scanned_rows=scanned,
                        updated_rows=changed,
                        last_seen_site_report_id=current.id,
                    )
                    last_hb_rows = scanned
                    last_hb_t = now_t
                continue

            if current.assets_started != calculated:
                current.assets_started = calculated
                current.save(update_fields=["assets_started"])
                changed += 1

                # Per-row progress log for monitoring while the one-off task runs.
                structured_logger.info(
                    "Backfilled assets_started for SiteReport.",
                    event_code="assets_started_backfill_row",
                    site_report_id=current.id,
                    created_on=current.created_on.isoformat(),
                    series=series_label,
                    assets_started=calculated,
                    previous_site_report_id=(previous.id if previous else None),
                    campaign_id=current.campaign_id,
                    topic_id=current.topic_id,
                )

            previous = current

            # Heartbeat while scanning
            now_t = time.monotonic()
            if (
                scanned - last_hb_rows >= HEARTBEAT_EVERY_ROWS
                or (now_t - last_hb_t) >= HEARTBEAT_EVERY_SECONDS
            ):
                structured_logger.info(
                    "Scanning series...",
                    event_code="assets_started_backfill_series_heartbeat",
                    series=series_label,
                    scanned_rows=scanned,
                    updated_rows=changed,
                    last_seen_site_report_id=current.id,
                )
                last_hb_rows = scanned
                last_hb_t = now_t

        structured_logger.info(
            "Finished series scan.",
            event_code="assets_started_backfill_series_done",
            series=series_label,
            scanned_rows=scanned,
            updated_rows=changed,
            elapsed_seconds=round(time.monotonic() - series_start_t, 3),
        )
        return changed

    # Site-wide TOTAL
    if SiteReport.objects.filter(
        report_name=SiteReport.ReportName.TOTAL,
        campaign__isnull=True,
        topic__isnull=True,
        assets_started__isnull=True,
    ).exists():
        total_qs = SiteReport.objects.filter(
            report_name=SiteReport.ReportName.TOTAL,
            campaign__isnull=True,
            topic__isnull=True,
        ).order_by("created_on", "pk")
        updated_count += process_series_queryset(total_qs, series_label="TOTAL")

    # Site-wide RETIRED_TOTAL
    if SiteReport.objects.filter(
        report_name=SiteReport.ReportName.RETIRED_TOTAL,
        assets_started__isnull=True,
    ).exists():
        retired_total_qs = SiteReport.objects.filter(
            report_name=SiteReport.ReportName.RETIRED_TOTAL
        ).order_by("created_on", "pk")
        updated_count += process_series_queryset(
            retired_total_qs, series_label="RETIRED_TOTAL"
        )

    # Per-campaign (includes retired campaigns; their historical reports remain)
    campaign_ids = (
        SiteReport.objects.filter(campaign__isnull=False, assets_started__isnull=True)
        .values_list("campaign_id", flat=True)
        .distinct()
    )
    for campaign_id in campaign_ids.iterator():
        campaign_series = SiteReport.objects.filter(campaign_id=campaign_id).order_by(
            "created_on", "pk"
        )
        updated_count += process_series_queryset(
            campaign_series, series_label=f"CAMPAIGN:{campaign_id}"
        )

    # Per-topic
    topic_ids = (
        SiteReport.objects.filter(topic__isnull=False, assets_started__isnull=True)
        .values_list("topic_id", flat=True)
        .distinct()
    )
    for topic_id in topic_ids.iterator():
        topic_series = SiteReport.objects.filter(topic_id=topic_id).order_by(
            "created_on", "pk"
        )
        updated_count += process_series_queryset(
            topic_series, series_label=f"TOPIC:{topic_id}"
        )

    structured_logger.info(
        "Completed backfill for assets_started.",
        event_code="assets_started_backfill_complete",
        updated_rows=updated_count,
        task_id=getattr(self.request, "id", None),
    )
    return updated_count
