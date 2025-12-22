import datetime
from collections.abc import Iterable
from time import time

from django.conf import settings
from django.db.models import Count, Max, Q, QuerySet
from django.db.models.functions import Greatest
from django.http import HttpRequest
from django.utils import timezone
from django.utils.timezone import now

from concordia.models import Asset, Transcription, TranscriptionStatus


def _get_pages(request: HttpRequest) -> QuerySet:
    """
    Retrieve a filtered and annotated queryset of assets based on user activity.

    Filters the Asset queryset by:
      - Activity type (transcribed or reviewed)
      - Transcription status
      - Date range (start, end or both)
      - Campaign ID
      - Last six months of activity

    Assets are annotated with:
      - Timestamps of last transcription/review activity
      - Combined latest activity timestamp

    Also applies ordering based on the selected sort parameter.

    Args:
        request (HttpRequest): The incoming HTTP request with query parameters.

    Returns:
        QuerySet: A queryset of `Asset` objects with applied filters and annotations.
    """
    user = request.user
    activity = request.GET.get("activity", None)

    if activity == "transcribed":
        q = Q(transcription__user=user)
    elif activity == "reviewed":
        q = Q(transcription__reviewed_by=user)
    else:
        q = Q(transcription__user=user) | Q(transcription__reviewed_by=user)
    assets = Asset.objects.filter(q)

    status_list = request.GET.getlist("status")
    if status_list and status_list != []:
        if "completed" not in status_list:
            assets = assets.exclude(transcription_status=TranscriptionStatus.COMPLETED)
        if "submitted" not in status_list:
            assets = assets.exclude(transcription_status=TranscriptionStatus.SUBMITTED)
        if "in_progress" not in status_list:
            assets = assets.exclude(
                transcription_status=TranscriptionStatus.IN_PROGRESS
            )

    assets = assets.select_related("item", "item__project", "item__project__campaign")

    assets = assets.annotate(
        last_transcribed=Max(
            "transcription__created_on",
            filter=Q(transcription__user=user),
        ),
        last_reviewed=Max(
            "transcription__updated_on",
            filter=Q(transcription__reviewed_by=user),
        ),
        latest_activity=Greatest(
            "last_transcribed",
            "last_reviewed",
            filter=Q(transcription__user=user) | Q(transcription__reviewed_by=user),
        ),
    )
    fmt = "%Y-%m-%d"
    start_date = None
    start = request.GET.get("start", None)
    if start is not None and len(start) > 0:
        start_date = timezone.make_aware(datetime.datetime.strptime(start, fmt))
    end_date = None
    end = request.GET.get("end", None)
    if end is not None and len(end) > 0:
        end_date = timezone.make_aware(datetime.datetime.strptime(end, fmt))
    if start_date is not None and end_date is not None:
        end_date += datetime.timedelta(days=1)
        end = end_date.strftime(fmt)
        assets = assets.filter(latest_activity__range=[start, end])
    elif start_date is not None or end_date is not None:
        date = start_date if start_date else end_date
        assets = assets.filter(
            latest_activity__year=date.year,
            latest_activity__month=date.month,
            latest_activity__day=date.day,
        )
    # CONCD-189 only show pages from the last 6 months
    # This should be an aware datetime, not a date. A date is cast
    # to a naive datetime when it's compared to a datetime
    # field, as is being done here
    SIX_MONTHS_AGO = now() - datetime.timedelta(days=6 * 30)
    assets = assets.filter(latest_activity__gte=SIX_MONTHS_AGO)
    order_by = request.GET.get("order_by", "date-descending")
    if order_by == "date-ascending":
        assets = assets.order_by("latest_activity", "-id")
    else:
        assets = assets.order_by("-latest_activity", "-id")

    campaign_id = request.GET.get("campaign", None)
    if campaign_id is not None:
        assets = assets.filter(item__project__campaign__pk=campaign_id)

    return assets


def calculate_asset_stats(asset_qs: QuerySet, ctx: dict) -> None:
    """
    Annotates the context dictionary with asset statistics and contributor data.

    Computes:
      - Total number of unique contributors across all transcriptions.
      - Count and percentage of assets per transcription status.
      - Labeled status counts for use in progress displays.

    Percentages are capped at 99% for values between 99.0 and 99.999... to avoid
    showing 100% prematurely.

    Args:
        asset_qs (QuerySet): A queryset of `Asset` objects to calculate statistics on.
        ctx (dict): The context dictionary to populate with computed values.

    Returns:
        None
    """
    asset_count = asset_qs.count()

    trans_qs = Transcription.objects.filter(asset__in=asset_qs).values_list(
        "user_id", "reviewed_by"
    )
    user_ids = set()
    for i, j in trans_qs.iterator():
        user_ids.add(i)
        user_ids.add(j)
    # Remove null values from the set, if it exists
    try:
        user_ids.remove(None)
    except KeyError:
        pass

    ctx["contributor_count"] = len(user_ids)

    asset_state_qs = asset_qs.values_list("transcription_status")
    asset_state_qs = asset_state_qs.annotate(Count("transcription_status")).order_by()
    status_counts_by_key = dict(asset_state_qs)

    ctx["transcription_status_counts"] = labeled_status_counts = []

    for status_key, status_label in TranscriptionStatus.CHOICES:
        value = status_counts_by_key.get(status_key, 0)
        if value:
            pct_raw = 100 * (value / asset_count)
            if pct_raw >= 99 and pct_raw < 100:
                pct = 99
            else:
                pct = round(pct_raw)
        else:
            pct = 0

        ctx[f"{status_key}_percent"] = pct
        ctx[f"{status_key}_count"] = value
        labeled_status_counts.append((status_key, status_label, value))


def annotate_children_with_progress_stats(children: Iterable) -> None:
    """
    Annotates child objects with transcription progress statistics.

    Each object is expected to have attributes named `{status}_count` corresponding to
    each transcription status key. This function calculates:

      - `total_count`: Total asset count for the object.
      - `{status}_percent`: Percentage of total for each transcription status.
      - `lowest_transcription_status`: The first non-zero status in defined order.

    Percentages are capped at 99% for values between 99.0 and 99.999... to avoid
    rounding up to 100% prematurely.

    Args:
        children (Iterable): A sequence of objects with `{status}_count` attributes.

    Returns:
        None
    """
    for obj in children:
        counts = {}

        for k, __ in TranscriptionStatus.CHOICES:
            counts[k] = getattr(obj, f"{k}_count", 0)

        obj.total_count = total = sum(counts.values())

        lowest_status = None

        for k, __ in TranscriptionStatus.CHOICES:
            count = counts[k]

            if total > 0:
                pct_raw = 100 * (count / total)
                if pct_raw >= 99 and pct_raw < 100:
                    pct = 99
                else:
                    pct = round(pct_raw)
            else:
                pct = 0

            setattr(obj, f"{k}_percent", pct)

            if lowest_status is None and count > 0:
                lowest_status = k

        obj.lowest_transcription_status = lowest_status


class AnonymousUserValidationCheckMixin:
    """
    Mixin that injects anonymous user validation context into class-based views.

    Adds a boolean `anonymous_user_validation_required` to the context, indicating
    whether a Turnstile validation prompt should be displayed based on the time since
    the user's last successful validation.

    Intended for use with views that already implement `get_context_data()`, such as
    Django's TemplateView or DetailView subclasses.
    """

    def get_context_data(self, *args, **kwargs) -> dict:
        """
        Add anonymous user validation flag to the context.

        If the user is unauthenticated and the time since their last validation exceeds
        the configured interval, the flag is set to True. Otherwise, it is set to False.

        Returns:
            dict: The updated template context with the validation flag included.
        """
        context = super().get_context_data(**kwargs)
        if not self.request.user.is_authenticated:
            turnstile_last_validated = self.request.session.get(
                "turnstile_last_validated", 0
            )
            age = time() - turnstile_last_validated
            context["anonymous_user_validation_required"] = (
                age > settings.ANONYMOUS_USER_VALIDATION_INTERVAL
            )
        else:
            context["anonymous_user_validation_required"] = False
        return context
