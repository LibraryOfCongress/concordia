import csv
from datetime import timedelta
from io import StringIO
from logging import getLogger

from django.core.cache import caches
from django.core.files.base import ContentFile
from django.db.models import Count
from django.utils import timezone

from concordia.decorators import locked_task
from concordia.logging import ConcordiaLogger
from concordia.models import Asset, Campaign, SiteReport, TranscriptionStatus
from concordia.storage import VISUALIZATION_STORAGE

from ..celery import app as celery_app

logger = getLogger(__name__)
structured_logger = ConcordiaLogger.get_logger(__name__)


@celery_app.task(bind=True, ignore_result=True)
@locked_task
def populate_asset_status_visualization_cache(self) -> None:
    """
    Build and cache aggregate asset status counts for active campaigns.

    This task queries live Asset rows for all campaigns that are published,
    listed and active then aggregates counts by ``transcription_status``. It
    also writes a CSV export to ``VISUALIZATION_STORAGE`` and stores the
    following payload in the ``"visualization_cache"`` under the
    ``"asset-status-overview"`` key:

        - `status_labels`: [
                "Not Started",
                "In Progress",
                "Needs Review",
                "Completed"
          ]
        - `total_counts`: [
                count_not_started,
                count_in_progress,
                count_submitted,
                count_completed
          ]
        - `csv_url`: URL to download a CSV of the data
    """
    visualization_cache = caches["visualization_cache"]
    cache_key = "asset-status-overview"
    csv_path = "visualization_exports/page-status-active-campaigns.csv"

    structured_logger.debug(
        "Starting asset status visualization task.",
        event_code="asset_status_vis_start",
    )

    campaign_ids = list(
        Campaign.objects.published().listed().active().values_list("id", flat=True)
    )

    status_keys = [key for key, _ in TranscriptionStatus.CHOICES]
    status_labels = [TranscriptionStatus.CHOICE_MAP[key] for key in status_keys]

    # Aggregate counts across all active campaigns
    status_counts_qs = (
        Asset.objects.filter(campaign_id__in=campaign_ids)
        .values("transcription_status")
        .annotate(cnt=Count("id"))
    )
    counts_map = {row["transcription_status"]: row["cnt"] for row in status_counts_qs}
    total_counts = [counts_map.get(status, 0) for status in status_keys]

    structured_logger.debug(
        "Aggregated asset counts by status.",
        event_code="asset_status_vis_counts",
        active_campaign_count=len(campaign_ids),
        total_counts=total_counts,
    )

    # If data unchanged, skip CSV + cache update
    existing = visualization_cache.get(cache_key)
    if isinstance(existing, dict) and existing.get("total_counts") == total_counts:
        structured_logger.info(
            "Asset status data unchanged; skipping CSV and cache update.",
            event_code="asset_status_vis_unchanged",
            total_counts=total_counts,
        )
        return
    elif isinstance(existing, dict):
        # We want the existing URL in case the upload fails later
        overview_csv_url = existing.get("csv_url")
    else:
        overview_csv_url = None

    overview_csv = StringIO(newline="")
    overview_writer = csv.writer(overview_csv)
    overview_writer.writerow(["Status", "Count"])
    for label, count in zip(status_labels, total_counts, strict=True):
        overview_writer.writerow([label, count])
    overview_csv_content = overview_csv.getvalue()

    try:
        VISUALIZATION_STORAGE.save(csv_path, ContentFile(overview_csv_content))
        overview_csv_url = VISUALIZATION_STORAGE.url(csv_path)
        structured_logger.debug(
            "CSV saved for asset status visualization.",
            event_code="asset_status_vis_csv_saved",
            csv_path=csv_path,
            byte_length=len(overview_csv_content.encode("utf-8")),
            csv_url=overview_csv_url,
        )
    except Exception:
        if overview_csv_url is None:
            structured_logger.exception(
                (
                    "CSV upload failed for asset status visualization and "
                    "no existing CSV URL could be determined"
                ),
                event_code="asset_status_vis_csv_missing_url_error",
                csv_path=csv_path,
            )
            raise
        structured_logger.exception(
            "CSV upload failed for asset status visualization.",
            event_code="asset_status_vis_csv_error",
            csv_path=csv_path,
        )

    # Update cache
    overview_payload = {
        "status_labels": status_labels,
        "total_counts": total_counts,
        "csv_url": overview_csv_url,
    }
    visualization_cache.set(cache_key, overview_payload, None)

    structured_logger.debug(
        "Asset status visualization cache updated.",
        event_code="asset_status_vis_cache_set",
        cache_key=cache_key,
        total_counts=total_counts,
    )

    structured_logger.debug(
        "Asset status visualization task completed successfully.",
        event_code="asset_status_vis_complete",
    )


@celery_app.task(bind=True, ignore_result=True)
@locked_task
def populate_daily_activity_visualization_cache(self) -> None:
    """
    Build and cache a 28 day time series of transcription activity.

    This task queries ``SiteReport`` rows with
    ``report_name=SiteReport.ReportName.TOTAL`` for the last 28 days
    (excluding today) and derives per day counts of saved transcriptions and
    review actions. It writes a CSV export to ``VISUALIZATION_STORAGE`` and
    stores the following payload in the ``"visualization_cache"`` under the
    ``"daily-transcription-activity-last-28-days"`` key.

    The dataset contains:

        - `labels`: [ "YYYY-MM-DD", ..., ] (28 dates)
        - `transcription_datasets`: [
              {
                  "label": "Transcriptions",
                  "data": [ daily_total, daily_total, ... ],
              },
              {
                  "label": "Reviews",
                  "data": [ daily_total, daily_total, ... ],
              },
          ]
        - `csv_url`: URL to download a CSV of the data
    """
    visualization_cache = caches["visualization_cache"]
    cache_key = "daily-transcription-activity-last-28-days"
    csv_path = "visualization_exports/daily-transcription-activity-last-28-days.csv"

    structured_logger.debug(
        "Starting daily activity visualization task.",
        event_code="daily_activity_vis_start",
    )

    yesterday = timezone.now().date() - timedelta(days=1)
    start_date = yesterday - timedelta(days=27)
    date_range = [start_date + timedelta(days=i) for i in range(28)]
    date_strings = [d.strftime("%Y-%m-%d") for d in date_range]

    reports = SiteReport.objects.filter(
        report_name=SiteReport.ReportName.TOTAL,
        created_on__date__in=date_range,
    )
    report_lookup = {report.created_on.date(): report for report in reports}

    # Find the most recent SiteReport BEFORE the first of our dates, if any
    prev_report = (
        SiteReport.objects.filter(
            report_name=SiteReport.ReportName.TOTAL,
            created_on__date__lt=start_date,
        )
        .order_by("-created_on")
        .first()
    )
    prev_cumulative = prev_report.transcriptions_saved if prev_report else 0
    running_prev = prev_cumulative

    transcriptions = []
    reviews = []

    for report_date in date_range:
        sitereport = report_lookup.get(report_date)
        if sitereport:
            cumulative = sitereport.transcriptions_saved or 0
            daily_saved = cumulative - running_prev
            if daily_saved < 0:
                daily_saved = 0
            running_prev = cumulative
            daily_review = sitereport.daily_review_actions or 0
        else:
            daily_saved = 0
            daily_review = 0

        transcriptions.append(daily_saved)
        reviews.append(daily_review)

    structured_logger.debug(
        "Compiled daily activity series.",
        event_code="daily_activity_vis_series_compiled",
        start_date=start_date.isoformat(),
        end_date=yesterday.isoformat(),
        transcriptions_total=sum(transcriptions),
        reviews_total=sum(reviews),
    )

    # If data unchanged, skip CSV + cache update
    existing = visualization_cache.get(cache_key)
    if isinstance(existing, dict):
        prev_series = existing.get("transcription_datasets") or []
        prev_transcriptions = next(
            (
                ds.get("data")
                for ds in prev_series
                if ds.get("label") == "Transcriptions"
            ),
            None,
        )
        prev_reviews = next(
            (ds.get("data") for ds in prev_series if ds.get("label") == "Reviews"),
            None,
        )
        if prev_transcriptions == transcriptions and prev_reviews == reviews:
            structured_logger.info(
                "Daily activity data unchanged; skipping CSV and cache update.",
                event_code="daily_activity_vis_unchanged",
            )
            return
        else:
            csv_url = existing.get("csv_url")
    else:
        csv_url = None

    data = {
        "labels": date_strings,
        "transcription_datasets": [
            {"label": "Transcriptions", "data": transcriptions},
            {"label": "Reviews", "data": reviews},
        ],
    }

    csv_output = StringIO(newline="")
    writer = csv.writer(csv_output)
    writer.writerow(["Date", "Transcriptions", "Reviews"])
    for i in range(28):
        writer.writerow([date_strings[i], transcriptions[i], reviews[i]])
    csv_content = csv_output.getvalue()

    try:
        VISUALIZATION_STORAGE.save(csv_path, ContentFile(csv_content))
        csv_url = VISUALIZATION_STORAGE.url(csv_path)
        structured_logger.debug(
            "CSV saved for daily activity visualization.",
            event_code="daily_activity_vis_csv_saved",
            csv_path=csv_path,
            byte_length=len(csv_content.encode("utf-8")),
            csv_url=csv_url,
        )
    except Exception:
        if csv_url is None:
            structured_logger.exception(
                (
                    "CSV upload failed for daily activity visualization and "
                    "no existing CSV URL could be determined"
                ),
                event_code="daily_activity_vis_csv_missing_url_error",
                csv_path=csv_path,
            )
            raise
        structured_logger.exception(
            "CSV upload failed for daily activity visualization.",
            event_code="daily_activity_vis_csv_error",
            csv_path=csv_path,
        )

    data["csv_url"] = csv_url
    visualization_cache.set(cache_key, data, None)

    structured_logger.debug(
        "Daily activity visualization cache updated.",
        event_code="daily_activity_vis_cache_set",
        cache_key=cache_key,
    )

    structured_logger.debug(
        "Daily activity visualization task completed successfully.",
        event_code="daily_activity_vis_complete",
    )
