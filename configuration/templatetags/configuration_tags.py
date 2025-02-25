from django import template

from configuration.models import Configuration
from configuration.utils import configuration_value as _configuration_value

register = template.Library()


@register.simple_tag
def configuration_value(key):
    """
    Retrieves the configuration value by key and returns its parsed value.
    """
    try:
        return _configuration_value(key)
    except (Configuration.DoesNotExist, Exception):
        # Return an empty string if the key doesn't exist or
        # get_value raises an exception of any type
        return ""
