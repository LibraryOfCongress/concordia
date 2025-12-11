from typing import Any

from django.conf import settings
from django.core.cache import caches

from configuration.models import Configuration

CONFIGURATION_KEY_PREFIX = "config"


def configuration_value(key: str) -> Any:
    """
    Retrieve a configuration value by key with caching and type casting.

    Behavior:
        - Look up the value in the ``configuration_cache`` using a namespaced
          cache key.
        - If the value is missing, delegate to
          ``cache_configuration_value(key)`` to fetch, cast, cache, and return
          the value.
        - Casting is performed by ``Configuration.get_value()`` based on the
          instance's ``data_type``.

    Caching:
        - Values are stored in the cache alias ``configuration_cache``.
        - Cache entries expire according to
          ``settings.CONFIGURATION_CACHE_TIMEOUT``.

    Args:
        key (str): The configuration key to resolve.

    Returns:
        Any: The resolved and type-cast configuration value.

    Raises:
        Configuration.DoesNotExist: If the key is not present in the database
            when attempting to populate the cache.
    """
    config_cache = caches["configuration_cache"]
    cache_key = f"{CONFIGURATION_KEY_PREFIX}_{key}"
    value = config_cache.get(cache_key)

    if value is None:
        value = cache_configuration_value(key)

    return value


def cache_configuration_value(key: str, value: Any | None = None) -> Any:
    """
    Populate or refresh the cached value for a configuration key.

    Behavior:
        - If ``value`` is ``None``, fetch the ``Configuration`` by ``key``,
          cast it via ``get_value()``, and cache the result.
        - If ``value`` is provided, cache that value directly.
        - Always write to the ``configuration_cache`` using the configured
          ``settings.CONFIGURATION_CACHE_TIMEOUT``.

    Args:
        key (str): The configuration key to cache.
        value (Any | None): An explicit value to cache. If ``None``, the value
            is loaded from the database and cast via ``get_value()``.

    Returns:
        Any: The value that was stored in the cache.

    Raises:
        Configuration.DoesNotExist: If ``value`` is ``None`` and there is no
            ``Configuration`` row with the given key.
    """
    config_cache = caches["configuration_cache"]
    cache_key = f"{CONFIGURATION_KEY_PREFIX}_{key}"

    if value is None:
        config = Configuration.objects.get(key=key)
        value = config.get_value()

    config_cache.set(cache_key, value, timeout=settings.CONFIGURATION_CACHE_TIMEOUT)
    return value
