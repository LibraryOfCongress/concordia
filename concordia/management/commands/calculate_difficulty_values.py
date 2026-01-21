"""
Management command to populate initial difficulty values.

Usage:
    python manage.py calculate_difficulty_values
    python manage.py calculate_difficulty_values --verbosity 2
"""

from timeit import default_timer

from django.core.management.base import BaseCommand

from concordia.tasks.assets import calculate_difficulty_values


class Command(BaseCommand):
    """
    Run the task which calculates initial difficulty values for assets.

    This command invokes `concordia.tasks.assets.calculate_difficulty_values()`
    and, when verbosity is greater than 1, prints how many records were
    updated and how long the run took.
    """

    def handle(self, *, verbosity: int, **kwargs) -> None:
        """
        Execute the command.

        Args:
            verbosity (int): Django's verbosity level (0, 1, 2, or 3).

        Returns:
            None
        """
        start_time = default_timer()

        updated_count = calculate_difficulty_values()

        if verbosity > 1:
            print(
                "Updated %d records in %0.1f seconds"
                % (updated_count, default_timer() - start_time)
            )
