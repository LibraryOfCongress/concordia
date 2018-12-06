from urllib.parse import quote as urlquote

from django import template

from ..models import TranscriptionStatus

register = template.Library()


@register.inclusion_tag("fragments/transcription-status-filters.html")
def transcription_status_filters(status_counts, active_value):
    ctx = {}

    ctx["status_choices"] = status_choices = [
        ("", "active" if not active_value else "", "", "All")
    ]

    for key, label in TranscriptionStatus.CHOICES:
        status_choices.append(
            (
                "?transcription_status=%s" % urlquote(key),
                "active" if active_value == key else "",
                key,
                label,
            )
        )

    return ctx
