from django.conf import settings
from django.core.cache import caches

from configuration.models import Configuration


def configuration_value(key):
    """
    Retrieves a configuration with the `key` and
    returns its value after casting it appropriately based
    on the Configuration's data_type.

    Caches the value in the `configuration_cache` for the time
    defined in the CONFIGURATION_CACHE_TIMEOUT setting.
    """
    config_cache = caches["configuration_cache"]
    cache_key = f"config_{key}"
    value = config_cache.get(cache_key)

    if value is None:
        config = Configuration.objects.get(key=key)
        value = config.get_value()
        config_cache.set(cache_key, value, timeout=settings.CONFIGURATION_CACHE_TIMEOUT)

    return value
