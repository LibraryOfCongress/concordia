from django.core.management.base import BaseCommand
from concordia.models import Collection, Asset, Status, MediaType

class Command(BaseCommand):
    args = '<foo bar ...>'
    help = 'This will populate the database with values needed to test the export with S3'

    def _add_data(self):
        """
        Add a collection with two items to db.  The 1st item has 5 assets and the second item
        has 3 assets

        """
        collection, created = Collection.objects.update_or_create(
            title="Test S3",
            slug="test_s3",
            description="Mockup test collection for S3 Storage",
            is_active=True,
            s3_storage=True,
            status=Status.EDIT)

        asset, created = Asset.objects.update_or_create(
            title="mss859430177",
            slug="mss8594301770",
            description="mss859430177",
            media_url="https://s3.us-east-2.amazonaws.com/chc-collections/test_s3/mss859430177/0.jpg",
            media_type=MediaType.IMAGE,
            collection=collection,
            metadata={"key": "val2"},
            sequence=0,
            status=Status.EDIT,
        )

        asset2, created = Asset.objects.update_or_create(
            title="mss859430177",
            slug="mss8594301771",
            description="mss859430177",
            media_url="https://s3.us-east-2.amazonaws.com/chc-collections/test_s3/mss859430177/1.jpg",
            media_type=MediaType.IMAGE,
            collection=collection,
            metadata={"key": "val2"},
            sequence=1,
            status=Status.EDIT,
        )

        asset3, created = Asset.objects.update_or_create(
            title="mss859430177",
            slug="mss8594301772",
            description="mss859430177",
            media_url="https://s3.us-east-2.amazonaws.com/chc-collections/test_s3/mss859430177/2.jpg",
            media_type=MediaType.IMAGE,
            collection=collection,
            metadata={"key": "val2"},
            sequence=2,
            status=Status.EDIT,
        )

        asset4, created = Asset.objects.update_or_create(
            title="mss859430177",
            slug="mss8594301773",
            description="mss859430177",
            media_url="https://s3.us-east-2.amazonaws.com/chc-collections/test_s3/mss859430177/3.jpg",
            media_type=MediaType.IMAGE,
            collection=collection,
            metadata={"key": "val2"},
            sequence=3,
            status=Status.EDIT,
        )

        asset5, created = Asset.objects.update_or_create(
            title="mss859430177",
            slug="mss8594301774",
            description="mss859430177",
            media_url="https://s3.us-east-2.amazonaws.com/chc-collections/test_s3/mss859430177/4.jpg",
            media_type=MediaType.IMAGE,
            collection=collection,
            metadata={"key": "val2"},
            sequence=4,
            status=Status.EDIT,
        )

        asset6, created = Asset.objects.update_or_create(
            title="mss859430178",
            slug="mss8594301780",
            description="mss859430178",
            media_url="https://s3.us-east-2.amazonaws.com/chc-collections/test_s3/mss859430178/0.png",
            media_type=MediaType.IMAGE,
            collection=collection,
            metadata={"key": "val2"},
            sequence=0,
            status=Status.EDIT,
        )

        asset7, created = Asset.objects.update_or_create(
            title="mss859430178",
            slug="mss8594301781",
            description="mss859430178",
            media_url="https://s3.us-east-2.amazonaws.com/chc-collections/test_s3/mss859430178/1.png",
            media_type=MediaType.IMAGE,
            collection=collection,
            metadata={"key": "val2"},
            sequence=1,
            status=Status.EDIT,
        )

        asset8, created = Asset.objects.update_or_create(
            title="mss859430178",
            slug="mss8594301782",
            description="mss859430178",
            media_url="https://s3.us-east-2.amazonaws.com/chc-collections/test_s3/mss859430178/2.png",
            media_type=MediaType.IMAGE,
            collection=collection,
            metadata={"key": "val2"},
            sequence=2,
            status=Status.EDIT,
        )

    def handle(self, *args, **options):
        self._add_data()
