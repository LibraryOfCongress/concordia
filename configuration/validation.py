import re

from django.core.exceptions import ValidationError

RATE_LIMIT_PATTERN = re.compile(r"^\d+/(s|m|h|d)$")


def validate_rate(rate: str) -> str:
    """
    Validate that a rate string matches the expected pattern like '10/m'.

    Behavior:
        - Strip leading and trailing whitespace.
        - Require the format '<positive integer>/<unit>' where unit is one of
          's', 'm', 'h', or 'd' (seconds, minutes, hours, days).
        - Return the cleaned string unchanged if valid.

    Args:
        rate (str): The candidate rate string to validate.

    Returns:
        str: The cleaned rate string if valid.

    Raises:
        ValidationError: If the input is not a string, if the format does not
            match the required pattern, or if the integer portion is less than
            or equal to zero.
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
