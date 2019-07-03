import csv
from datetime import datetime

from django.core.management.base import BaseCommand

from concordia.models import Campaign, SiteReport


class Command(BaseCommand):
    help = "Import CSV Site Report data"  # NOQA: A003

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv-file",
            default="site_reports.csv",
            help="Path to CSV file to import (default=%(default)s)",
        )

    def handle(self, *, csv_file, **options):
        with open(csv_file, "r") as csv_file:
            reader = csv.reader(csv_file, delimiter=",")
            header = reader.__next__()
            for row in reader:
                site_report_data = {key: value for key, value in zip(header, row)}
                site_report = dict()

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
