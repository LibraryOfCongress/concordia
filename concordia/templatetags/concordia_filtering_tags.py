from typing import Any, Dict, Iterable, List, Tuple
from urllib.parse import quote as urlquote

from django import template

from ..models import TranscriptionStatus

register = template.Library()


@register.inclusion_tag("fragments/transcription-status-filters.html")
def transcription_status_filters(
    status_counts: Iterable[Tuple[str, str, int]],
    active_value: str | None,
    size: str = "small",
    reversed_order: bool = False,
    url: str = "",
) -> Dict[str, Any]:
    """
    Build a context for the transcription status filter UI.

    Behavior:
        Produces the context expected by the
        `fragments/transcription-status-filters.html` template. The context
        includes a `status_choices` list of tuples used to render links and
        classes for each status, plus an entry representing "All."

        The function keeps the provided `active_value` selected, can reverse
        the status order, and will prepend the provided `url` when building
        filter links.

    Usage:
        Basic usage with counts from the view:

            {% load concordia_filtering_tags %}
            {% transcription_status_filters status_counts active_value %}

        With optional parameters:

            {% transcription_status_filters status_counts active_value
               size="small" reversed_order=True url=request.path %}

        Where:
            - `status_counts` is an iterable of `(key, label, count)`.
            - `active_value` is the currently selected status key, or empty.
            - `size` controls sizing classes used by the fragment.
            - `reversed_order` reverses the order of `TranscriptionStatus.CHOICES`.
            - `url` is prefixed to each generated link.

    Args:
        status_counts: Iterable of three-tuples `(key, label, count)` used to
            display per-status counts.
        active_value: The currently active status key, or `None`/empty for All.
        size: Size hint passed through to the template.
        reversed_order: If True, reverse the status choice order.
        url: Base URL to which the query string is appended.

    Returns:
        dict: Template context with keys:
            - `size` (str)
            - `status_choices` (list[tuple[str, str, str, str, int | None]])
              Each tuple is `(href, active_class, css_key, label, count)`.
    """
    ctx: Dict[str, Any] = {}
    ctx["size"] = size

    status_choices: List[Tuple[str, str, str, str, int | None]] = [
        ("", "flex-initial" + " active" if not active_value else "", "", "All", None)
    ]
    ctx["status_choices"] = status_choices

    counts = {count[0]: count[2] for count in status_counts}
    statuses = TranscriptionStatus.CHOICES
    if reversed_order:
        statuses = reversed(statuses)
    for key, label in statuses:
        status_choices.append(
            (
                "%s?transcription_status=%s" % (url, urlquote(key)),
                "active" if active_value == key else "",
                key.replace("_", "-"),
                label,
                counts.get(key),
            )
        )

    return ctx
