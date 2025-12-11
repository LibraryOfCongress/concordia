"""
Import CSV Site Report data into the database.

This command reads a CSV file, maps each row to `SiteReport` fields and
creates `SiteReport` rows. If a "campaign" column is present and non-empty,
its value is treated as a `Campaign.id` and looked up before creation.

Usage:
    python manage.py import_site_reports --csv-file path/to/file.csv

Arguments:
    --csv-file  Path to the CSV file. Defaults to "site_reports.csv".

CSV expectations:
    - The first row is a header. Field names must match `SiteReport` fields,
      except:
        * "time" is combined with "created_on" to form a single datetime.
    - Empty strings are ignored and not included in the create kwargs.
    - "created_on" and "time" are combined then parsed with the format:
        %m/%d/%Y %I:%M %p %Z
      Example: "04/30/2024 09:15 AM UTC"
    - "campaign" is optional. If present and non-empty, it must be a valid
      `Campaign.id`.

Notes:
    - Rows are created one by one. This is intentional to match current
      behavior.
"""

import csv
from argparse import ArgumentParser
from datetime import datetime

from django.core.management.base import BaseCommand

from concordia.models import Campaign, SiteReport


class Command(BaseCommand):
    help = "Import CSV Site Report data"  # NOQA: A003

    def add_arguments(self, parser: ArgumentParser) -> None:
        """
        Add the --csv-file argument with a sensible default.

        Args:
            parser: The Django command argument parser.
        """
        parser.add_argument(
            "--csv-file",
            default="site_reports.csv",
            help="Path to CSV file to import (default=%(default)s)",
        )

    def handle(self, *, csv_file: str, **options) -> None:
        """
        Read the CSV, normalize fields and create `SiteReport` rows.

        Behavior:
            - Reads the header row to build a name->value mapping for each row.
            - Drops keys with empty-string values.
            - Concatenates "created_on" and "time" to a single string,
              parses with `%m/%d/%Y %I:%M %p %Z`, assigns to "created_on".
            - Removes the "time" key after parsing.
            - If "campaign" is present, replaces it with the model instance
              using `Campaign.objects.get(id=...)`.
            - Creates a `SiteReport` with the remaining data.

        Args:
            csv_file: Path to the CSV file to import.

        Returns:
            None
        """
        with open(csv_file, "r") as csv_file:
            reader = csv.reader(csv_file, delimiter=",")
            header = reader.__next__()
            for row in reader:
                site_report_data = dict(zip(header, row, strict=True))
                site_report = {}

                for key in site_report_data:
                    if site_report_data[key] != "":
                        site_report[key] = site_report_data[key]

                site_report["created_on"] = "%s %s" % (
                    site_report["created_on"],
                    site_report["time"],
                )

                site_report["created_on"] = datetime.strptime(
                    site_report["created_on"], "%m/%d/%Y %I:%M %p %Z"
                )

                site_report.pop("time")

                if site_report.get("campaign"):
                    campaign = Campaign.objects.get(id=site_report["campaign"])
                    site_report["campaign"] = campaign

                SiteReport.objects.create(**site_report)
