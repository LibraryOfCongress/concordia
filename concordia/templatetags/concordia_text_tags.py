import re

from django import template
from urllib.parse import quote_plus

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
def urlencode_text(text):
    return quote_plus(text)
