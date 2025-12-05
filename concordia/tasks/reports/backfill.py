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
    Backfill the ``assets_started`` field for existing site-report series.

    This one-off task computes and persists ``assets_started`` values for all
    relevant ``SiteReport`` rows. It should be removed after it has been run in
    production and the backfill is no longer needed.

    Series processed:

    * Site-wide TOTAL (``report_name=TOTAL``)
    * Site-wide RETIRED_TOTAL (``report_name=RETIRED_TOTAL``)
    * Per-campaign (``campaign`` is not null)
    * Per-topic (``topic`` is not null)

    Rules:

    * The first snapshot in each series assumes ``assets_started = 0``. This
      represents the launch of the site or the time before the first report
      when no earlier data is available.
    * If there are gaps in days, the previous value is taken from the most
      recent prior report in that series.
    * Per-row values are derived from ``assets_total`` and
      ``assets_not_started``; publish/unpublish changes alone do not affect
      ``assets_started`` as long as the total and not-started counts remain
      consistent.
    * All results are floored at 0, since negative values indicate data
      removal and should not be treated as negative activity.

    Resumability:

    * By default, rows that already have a non-null ``assets_started`` value
      are skipped (``skip_existing=True``), so the task can be re-run to
      resume where it left off. In this mode, only series that still contain
      at least one snapshot with ``assets_started`` set to ``NULL`` are
      processed.
    * To recompute all rows, for example after changing the formula, call the
      task with ``skip_existing=False``. In this mode, any series that has at
      least one snapshot is processed, even if all snapshots already have
      non-null ``assets_started`` values.

    Args:
        skip_existing: If true, skip rows where ``assets_started`` is already
            populated.

    Returns:
        The number of ``SiteReport`` rows updated across all series.
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
        force_zero_assets_started: bool = False,
    ) -> int:
        """
        Process a single series in chronological order and backfill values.

        This helper walks one site-report series and computes
        ``assets_started`` for each row based on the previous snapshot. It
        saves updated rows and logs progress, including periodic heartbeat
        messages for monitoring long-running scans.

        For rollup series whose membership can change over time (for example,
        ``RETIRED_TOTAL``), the delta-based ``assets_started`` calculation is
        not meaningful. In those cases, callers should set
        ``force_zero_assets_started=True`` to backfill a consistent zero value.

        Args:
            qs: Queryset or iterable of ``SiteReport`` objects ordered by
                ``created_on`` and primary key.
            series_label: Short label for logging, such as ``"TOTAL"`` or
                ``"CAMPAIGN:<id>"``.
            force_zero_assets_started: If True, set ``assets_started`` to 0 for
                every row in the series instead of computing deltas between
                snapshots.

        Returns:
            The number of rows in the series that were updated.
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

            if force_zero_assets_started:
                calculated = 0
            elif previous is None:
                calculated = 0
            else:
                calculated = SiteReport.calculate_assets_started(
                    previous_assets_total=previous.assets_total,
                    previous_assets_not_started=previous.assets_not_started,
                    current_assets_total=current.assets_total,
                    current_assets_not_started=current.assets_not_started,
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

                # Per-row progress log for monitoring while the one-off task
                # runs.
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
    total_base_qs = SiteReport.objects.filter(
        report_name=SiteReport.ReportName.TOTAL,
        campaign__isnull=True,
        topic__isnull=True,
    )
    total_exists_qs = total_base_qs
    if skip_existing:
        total_exists_qs = total_exists_qs.filter(assets_started__isnull=True)

    if total_exists_qs.exists():
        total_qs = total_base_qs.order_by("created_on", "pk")
        updated_count += process_series_queryset(total_qs, series_label="TOTAL")

    # Site-wide RETIRED_TOTAL
    retired_base_qs = SiteReport.objects.filter(
        report_name=SiteReport.ReportName.RETIRED_TOTAL
    )
    retired_exists_qs = retired_base_qs
    if skip_existing:
        retired_exists_qs = retired_exists_qs.filter(assets_started__isnull=True)

    if retired_exists_qs.exists():
        retired_total_qs = retired_base_qs.order_by("created_on", "pk")
        updated_count += process_series_queryset(
            retired_total_qs,
            series_label="RETIRED_TOTAL",
            force_zero_assets_started=True,
        )

    # Per-campaign (includes retired campaigns; their historical reports remain)
    campaign_base_qs = SiteReport.objects.filter(campaign__isnull=False)
    if skip_existing:
        campaign_ids_source = campaign_base_qs.filter(assets_started__isnull=True)
    else:
        campaign_ids_source = campaign_base_qs

    campaign_ids = campaign_ids_source.values_list("campaign_id", flat=True).distinct()
    for campaign_id in campaign_ids.iterator():
        campaign_series = campaign_base_qs.filter(campaign_id=campaign_id).order_by(
            "created_on", "pk"
        )
        updated_count += process_series_queryset(
            campaign_series, series_label=f"CAMPAIGN:{campaign_id}"
        )

    # Per-topic
    topic_base_qs = SiteReport.objects.filter(topic__isnull=False)
    if skip_existing:
        topic_ids_source = topic_base_qs.filter(assets_started__isnull=True)
    else:
        topic_ids_source = topic_base_qs

    topic_ids = topic_ids_source.values_list("topic_id", flat=True).distinct()
    for topic_id in topic_ids.iterator():
        topic_series = topic_base_qs.filter(topic_id=topic_id).order_by(
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
