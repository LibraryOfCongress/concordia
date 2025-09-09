from django.core.cache import caches
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Fetch a value from the configuration cache by key."  # NOQA: A003

    def add_arguments(self, parser):
        parser.add_argument("key", type=str, help="The cache key to retrieve")

    def handle(self, *args, **options):
        config_cache = caches["configuration_cache"]
        key = options["key"]
        cache_key = f"config_{key}"
        value = config_cache.get(cache_key)

        if value is None:
            self.stdout.write(self.style.WARNING(f"Key '{key}' not found in cache."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Key '{key}' found:"))
            self.stdout.write(str(value))
