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
