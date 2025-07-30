from django.db.models.signals import post_save
from django.dispatch import receiver

from configuration.models import Configuration
from configuration.utils import cache_configuration_value


@receiver(post_save, sender=Configuration)
def update_cached_configuration_value(sender, *, instance, **kwargs):
    cache_configuration_value(instance.key, instance.get_value())
