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
def reprchar(character: str) -> str:
    """
    Return a Python-style literal representation of `character`
    without the surrounding quotes, e.g. '\\u200b', '\\x00', '\\n'.
    """
    return repr(character)[1:-1]  # strip the outer quotes
