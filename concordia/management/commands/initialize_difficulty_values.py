from django.core.management.base import BaseCommand

from concordia.models import Asset
from django.db.models import Count


class Command(BaseCommand):
    help = "Initializes difficulty attribute in Asset model"

    def handle(self, **options):
        assets = Asset.objects.published().annotate(
            transcription_count=Count("transcription", distinct=True),
            contributor_count=Count("transcription__user", distinct=True),
            reviewer_count=Count("transcription__reviewed_by", distinct=True),
        )

        for a in assets:
            a.difficulty = a.transcription_count * (
                a.contributor_count + a.reviewer_count
            )
            a.save()
