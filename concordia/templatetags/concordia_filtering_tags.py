from urllib.parse import quote as urlquote

from django import template

from ..models import TranscriptionStatus

register = template.Library()


@register.inclusion_tag("fragments/transcription-status-filters.html")
def transcription_status_filters(status_counts, active_value):
    ctx = {}

    status_count_map = {key: count for key, label, count in status_counts}
    total_count = sum(status_count_map.values())

    ctx["status_choices"] = status_choices = [
        ("", "active" if not active_value else "", f"All ({total_count})")
    ]

    for key, label in TranscriptionStatus.CHOICES:
        asset_count = status_count_map.get(key, 0)
        status_choices.append(
            (
                "?transcription_status=%s" % urlquote(key),
                "active" if active_value == key else "",
                f"{label} ({asset_count})",
            )
        )

    return ctx
