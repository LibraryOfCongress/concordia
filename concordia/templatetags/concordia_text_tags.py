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
    truncate = len(value) > 26
    while len(value) > 26:
        words = value.split()
        words = words[1:]
        value = " ".join(words)
    if truncate:
        value = "...%s" % value
    return value
