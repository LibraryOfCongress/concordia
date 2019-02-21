from django.core.management.base import BaseCommand
from concordia.models import AssetTag


class Command(BaseCommand):
    help = "Dedupe flattened tags"

    def handle(self, **options):
        flat_tags = AssetTag.objects.all()

        for each_tag in flat_tags:
            # Check whether there are any other instances of the same tag text and asset
            duplicate_tags = AssetTag.objects.filter(
                tag_text=each_tag.tag_text, asset=each_tag.asset
            ).order_by("created_on")
            if duplicate_tags.count() > 1:
                for duplicate_tag in duplicate_tags[1:]:
                    duplicate_tag.delete()
