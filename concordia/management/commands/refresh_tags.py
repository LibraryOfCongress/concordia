from django.core.management.base import BaseCommand
from concordia.models import AssetTag, Tag, UserAssetTagCollection


class Command(BaseCommand):
    help = "Repopulate tags"

    def handle(self, **options):

        # Once all the data has been flattened and de-duped,
        # then delete the original data
        UserAssetTagCollection.objects.all().delete()
        Tag.objects.all().delete()

        # And repopulate Tags, linking created Tag objects to their AssetTag instances
        fresh_flat_tags = AssetTag.objects.all()
        for flat_tag in fresh_flat_tags:
            # FIXME: make case-insensitive on get, sensitive on create
            distinct_tag, created = Tag.objects.get_or_create(value=flat_tag.tag_text)
            flat_tag.tag = distinct_tag
            flat_tag.save()
