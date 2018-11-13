"""
Print a list of URLs using the local database suitable for front-end testing
"""

from urllib.parse import urljoin

from django.core.management.base import BaseCommand
from django.urls import reverse

from concordia.models import Asset


class Command(BaseCommand):
    help = "Print URLs for front-end testing"

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-url",
            default="http://localhost:8000/",
            help="Change the base URL for all generated URLs from %(default)s",
        )

    def handle(self, *, base_url, **options):
        paths = [
            reverse("homepage"),
            reverse("about"),
            reverse("latest"),
            reverse("contact"),
            # Help pages
            reverse("help-center"),
            reverse("welcome-guide"),
            reverse("how-to-transcribe"),
            reverse("how-to-review"),
            reverse("how-to-tag"),
            reverse("for-educators"),
            reverse("questions"),
            # Account pages
            reverse("registration_register"),
            reverse("registration_login"),
            reverse("password_reset"),
            reverse("login"),
            reverse("transcriptions:campaign-list"),
        ]

        # Database content
        # First we'll find an asset which is actually visible:
        asset_qs = Asset.objects.filter(
            published=True,
            item__published=True,
            item__project__published=True,
            item__project__campaign__published=True,
        )
        if asset_qs.exists():
            asset = asset_qs.first()
            item = asset.item
            project = item.project
            campaign = project.campaign

            paths.extend(
                [
                    reverse(
                        "transcriptions:asset-detail",
                        kwargs={
                            "campaign_slug": campaign.slug,
                            "project_slug": project.slug,
                            "item_id": item.item_id,
                            "slug": asset.slug,
                        },
                    ),
                    reverse(
                        "transcriptions:item-detail",
                        kwargs={
                            "campaign_slug": campaign.slug,
                            "project_slug": project.slug,
                            "item_id": item.item_id,
                        },
                    ),
                    reverse(
                        "transcriptions:project-detail",
                        kwargs={"campaign_slug": campaign.slug, "slug": project.slug},
                    ),
                    reverse(
                        "transcriptions:campaign-detail", kwargs={"slug": campaign.slug}
                    ),
                ]
            )
        for path in sorted(paths):
            print(urljoin(base_url, path))
