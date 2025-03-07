from django import template

register = template.Library()


@register.filter
def reject(value, args):
    """
    Removes one or more unwanted items from a list or space-separated string.
    - If `value` is a list, removes any matching elements.
    - If `value` is a space-separated string (like CSS classes),
        removes the matching items and preserves formatting.
    - If multiple items should be rejected,
        pass them as a comma-separated string (e.g., `"safe,info"`).

    Example Usage:
    {{ "error warn marked-safe"|reject:"marked-safe" }}  -> "error warn"
    {{ "error warning marked-safe"|reject:"marked-safe,warn" }}  -> "error"
    {{ ["error", "warn", "marked-safe"]|reject:"marked-safe" }}  -> ["error", "warn"]
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
