import re

from django import template

register = template.Library()

WHITESPACE_NORMALIZER = re.compile(r"\s+")


@register.filter
def normalize_whitespace(text):
    """
    Return the provided text after with all consecutive whitespace replaced with
    a single space
    """
    return WHITESPACE_NORMALIZER.sub(" ", text)


@register.filter
def truncate_left(value):
    """
    Similar to the built-in truncatewords filter, but instead
    truncate before `arg` number of words (rather than after).
    """
    MAX_CHARS = 26
    truncate = len(value) > MAX_CHARS
    while len(value) > MAX_CHARS:
        _, value = value.split(maxsplit=1)
    if truncate:
        value = "...%s" % value
    return value
