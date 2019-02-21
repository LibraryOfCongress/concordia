from django.core.management.base import BaseCommand
from concordia.models import AssetTag, UserAssetTagCollection


class Command(BaseCommand):
    help = "Flatten tags"

    def handle(self, **options):

        all_tags = UserAssetTagCollection.objects.all()

        for tag_collection in all_tags:
            for tag in tag_collection.tags.all():
                # Add each row as an AssetTag object
                new_flat_tag = AssetTag(
                    tag_text=tag.value,
                    asset=tag_collection.asset,
                    user=tag_collection.user,
                    created_on=tag_collection.created_on,
                    updated_on=tag_collection.updated_on,
                )
                new_flat_tag.save()
