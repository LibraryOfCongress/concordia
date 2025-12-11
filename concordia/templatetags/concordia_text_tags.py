import re

from django import template

register = template.Library()

WHITESPACE_NORMALIZER = re.compile(r"\s+")


@register.filter
def normalize_whitespace(text: str) -> str:
    """
    Replace consecutive whitespace in text with a single space.

    Behavior:
        Collapses runs of whitespace characters (including newlines and tabs)
        to a single ASCII space.

    Usage:
        In a template:

            {% load concordia_text_tags %}
            {{ some_text|normalize_whitespace }}

        In Python:

            normalize_whitespace("a\\n\\n  b\\t\\t c")  # -> "a b c"

    Args:
        text: Input text to normalize.

    Returns:
        str: Text with whitespace collapsed to single spaces.
    """
    return WHITESPACE_NORMALIZER.sub(" ", text)


@register.filter
def reprchar(character: str) -> str:
    """
    Return a Python-style literal representation of a single character without
    surrounding quotes, for example "\\\\u200b", "\\\\x00", "\\\\n".

    Behavior:
        Uses Python's `repr` to obtain an escaped form, then removes the outer
        quotes so the result is suitable for display in templates.

    Usage:
        In a template:

            {% load concordia_text_tags %}
            Invisible char: {{ some_char|reprchar }}

        In Python:

            reprchar("\\u200b")  # -> "\\\\u200b"

    Args:
        character: A single-character string to represent.

    Returns:
        str: The escaped representation without surrounding quotes.
    """
    # Strip the outer quotes added by repr
    return repr(character)[1:-1]
