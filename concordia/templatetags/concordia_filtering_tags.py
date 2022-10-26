from urllib.parse import quote as urlquote

from django import template

from ..models import TranscriptionStatus

register = template.Library()


@register.inclusion_tag("fragments/transcription-status-filters.html")
def transcription_status_filters(
    status_counts, active_value, size="small", reversed_order=False
):
    ctx = {}
    ctx["size"] = size

    ctx["status_choices"] = status_choices = [
        ("", "flex-initial" + " active" if not active_value else "", "", "All", None)
    ]

    counts = {count[0]: count[2] for count in status_counts}
    statuses = TranscriptionStatus.CHOICES
    if reversed_order:
        statuses = reversed(statuses)
    for key, label in statuses:
        status_choices.append(
            (
                "?transcription_status=%s" % urlquote(key),
                "active" if active_value == key else "",
                key,
                label,
                counts.get(key),
            )
        )

    return ctx
