import datetime
from time import time

from django.conf import settings
from django.contrib import messages
from django.db.models import Count, Max, Q
from django.db.models.functions import Greatest
from django.utils import timezone
from django.utils.timezone import now

from concordia.models import Asset, Transcription, TranscriptionStatus

ASSETS_PER_PAGE = 36
PROJECTS_PER_PAGE = 36
ITEMS_PER_PAGE = 36
URL_REGEX = r"http[s]?://"

MESSAGE_LEVEL_NAMES = dict(
    zip(
        messages.DEFAULT_LEVELS.values(),
        map(str.lower, messages.DEFAULT_LEVELS.keys()),
        strict=False,
    )
)


def _get_pages(request):
    user = request.user
    activity = request.GET.get("activity", None)

    if activity == "transcribed":
        q = Q(user=user)
    elif activity == "reviewed":
        q = Q(reviewed_by=user)
    else:
        q = Q(user=user) | Q(reviewed_by=user)
    transcriptions = Transcription.objects.filter(q)

    assets = Asset.objects.filter(transcription__in=transcriptions)
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


def calculate_asset_stats(asset_qs, ctx):
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


def annotate_children_with_progress_stats(children):
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
    def get_context_data(self, *args, **kwargs):
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
