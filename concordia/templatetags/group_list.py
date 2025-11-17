from typing import Any, Sequence

from django import template

register = template.Library()


@register.filter
def batch(value: Sequence[Any], size: int) -> list[Sequence[Any]]:
    """
    Group a sequence into consecutive chunks.

    Behavior:
        Returns a list of slices from `value`, each of length `size`, except
        possibly the last slice if there are not enough elements.

    Usage:
        In a template:

            {% load group_list %}
            {% for row in items|batch:3 %}
                <div class="row">
                    {% for item in row %}
                        <span>{{ item }}</span>
                    {% endfor %}
                </div>
            {% endfor %}

        In Python:

            batch([1, 2, 3, 4, 5], 2)  # -> [[1, 2], [3, 4], [5]]
            batch(("a", "b", "c"), 4)  # -> [("a", "b", "c")]

    Args:
        value: The sequence to split. Must support `len()` and slicing.
        size: The maximum size of each chunk. Will be converted to `int`
            by Django when called from templates.

    Returns:
        list[Sequence[Any]]: Consecutive slices of `value`, each at most `size`
        elements long.
    """
    size = int(size)
    return [value[i : i + size] for i in range(0, len(value), size)]
