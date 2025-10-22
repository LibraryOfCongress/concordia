"""
Run the task which calculates initial difficulty values
"""

from timeit import default_timer

from django.core.management.base import BaseCommand

from concordia.tasks.assets import calculate_difficulty_values


class Command(BaseCommand):
    def handle(self, *, verbosity, **kwargs):
        start_time = default_timer()

        updated_count = calculate_difficulty_values()

        if verbosity > 1:
            print(
                "Updated %d records in %0.1f seconds"
                % (updated_count, default_timer() - start_time)
            )
