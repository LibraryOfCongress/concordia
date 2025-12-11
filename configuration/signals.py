from django.db.models.signals import post_save
from django.dispatch import receiver

from configuration.models import Configuration
from configuration.utils import cache_configuration_value


@receiver(post_save, sender=Configuration)
def update_cached_configuration_value(
    sender: type[Configuration], *, instance: Configuration, **kwargs
) -> None:
    """
    Post-save signal handler that updates the cached configuration value.

    Behavior:
        - Parse the instance value using `Configuration.get_value()`.
        - If parsing succeeds, write the parsed value to the cache via
          `cache_configuration_value`.
        - If parsing raises any exception, skip caching to avoid persisting an
          invalid value.

    Signals:
        Connected to `django.db.models.signals.post_save` for
        `configuration.models.Configuration`.

    Args:
        sender (type[Configuration]): The model class that sent the signal.
        instance (Configuration): The saved instance whose parsed value should
            be cached.

    Returns:
        None
    """
    try:
        value = instance.get_value()
    except Exception:
        # Do not cache if value is invalid
        return
    cache_configuration_value(instance.key, value)
