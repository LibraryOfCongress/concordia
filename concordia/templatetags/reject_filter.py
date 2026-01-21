from typing import Any

from django import template

register = template.Library()


@register.filter
def reject(value: Any, args: str) -> Any:
    """
    Remove one or more unwanted items from a list or space-separated string.

    Behavior:
        - If `value` is a string, treat it as space-separated tokens.
        - If `value` is an iterable of items, convert it to a list.
        - Remove any tokens present in `args`, which is a comma-separated
          string of items to reject.

    Usage:
        In a template:

            {% load reject_filter %}
            {{ "error warn marked-safe"|reject:"marked-safe" }}
            {# -> "error warn" #}

            {{ "error warning marked-safe"|reject:"marked-safe,warn" }}
            {# -> "error" #}

            {{ my_list|reject:"deprecated,hidden" }}
            {# If my_list == ["ok", "deprecated", "x", "hidden"] then
               -> ["ok", "x"] #}

        In Python:

            reject("a b c", "b")            # -> "a c"
            reject(["a", "b", "c"], "b,c")  # -> ["a"]

    Args:
        value: Input to filter. A space-separated string or an iterable.
        args: Comma-separated items to remove.

    Returns:
        If `value` is a string, a space-joined string of remaining tokens.
        Otherwise a list of remaining items.
    """
    if not value:
        return value

    if isinstance(value, str):
        value_list = value.split()
    else:
        value_list = list(value)

    reject_items = set(args.split(","))

    filtered_list = [item for item in value_list if item not in reject_items]

    return " ".join(filtered_list) if isinstance(value, str) else filtered_list
