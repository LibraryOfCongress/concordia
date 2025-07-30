import re

from django.core.exceptions import ValidationError

RATE_LIMIT_PATTERN = re.compile(r"^\d+/(s|m|h|d)$")


def validate_rate(rate: str) -> str:
    """
    Validate that a string is a valid rate limit pattern (e.g., '10/m').

    Leading/trailing whitespace is stripped before validation.

    Raises:
        ValidationError: if the format is invalid or value is nonsensical.

    Returns:
        str: The cleaned rate string if valid.
    """
    if not isinstance(rate, str):
        raise ValidationError("Rate limit must be a string.")

    rate = rate.strip()

    if not RATE_LIMIT_PATTERN.match(rate):
        raise ValidationError("Invalid rate limit format. Use '<number>/<s|m|h|d>'.")

    count, unit = rate.split("/")
    if int(count) <= 0:
        raise ValidationError("Rate limit count must be greater than 0.")

    return rate
