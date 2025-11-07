from typing import Any

from django import template

from configuration.models import Configuration
from configuration.utils import configuration_value as _configuration_value

register = template.Library()


@register.simple_tag
def configuration_value(key: str) -> Any:
    """
    Return the parsed configuration value for a key, for use in templates.

    Behavior:
        Delegates to `configuration.utils.configuration_value` to fetch and parse
        the value (including any casting based on the configured data type).
        If the configuration is missing or parsing raises an exception of any
        kind, return an empty string to keep template rendering resilient.

    Args:
        key (str): The unique configuration key.

    Returns:
        Any: The parsed value when available and valid; otherwise an empty string.
    """
    try:
        return _configuration_value(key)
    except (Configuration.DoesNotExist, Exception):
        # Return an empty string if the key does not exist or parsing fails
        return ""
