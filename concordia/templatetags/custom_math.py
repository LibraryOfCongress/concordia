from typing import Any

from django import template

register = template.Library()


@register.filter(name="multiply")
def multiply(value: Any, arg: Any) -> Any:
    """
    Multiply two values.

    Behavior:
        Returns the product of `value` and `arg` using Python's `*` operator.

    Usage:
        In a template:

            {% load custom_math %}
            {{ 6|multiply:7 }}            {# 42 #}
            {{ price|multiply:quantity }} {# product of variables #}

        In Python:

            multiply(3, 5)   # -> 15
            multiply("a", 3) # -> "aaa"

    Args:
        value: Left operand.
        arg: Right operand.

    Returns:
        Any: The result of `value * arg`.
    """
    return value * arg
