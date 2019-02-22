from django.core.management.base import BaseCommand

from concordia.models import Asset


class Command(BaseCommand):
    help = "Populate the year attribute for Assets"

    def handle(self, **options):
        assets = Asset.objects.all().prefetch_related("item")
        for asset in assets:
            metadata = asset.item.metadata
            date_info = metadata["item"]["dates"][0]
            for asset_date in date_info:
                asset.year = asset_date
                asset.save()
