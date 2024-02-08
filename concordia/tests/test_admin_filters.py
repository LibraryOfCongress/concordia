from django.test import TestCase
from django.utils import timezone

from concordia.admin import TranscriptionAdmin
from concordia.admin.filters import SubmittedFilter
from concordia.models import Transcription
from concordia.tests.utils import CreateTestUsers, create_transcription


class NullableTimestampFilterTest(CreateTestUsers, TestCase):
    def setUp(self):
        user = self.create_user(username="tester")
        create_transcription(user=user, submitted=timezone.now())

    def test_lookups(self):
        f = SubmittedFilter(
            None, {"submitted": "null"}, Transcription, TranscriptionAdmin
        )
        transcriptions = f.queryset(None, Transcription.objects.all())
        self.assertEqual(transcriptions.count(), 0)

        f = SubmittedFilter(
            None, {"submitted": "not-null"}, Transcription, TranscriptionAdmin
        )
        transcriptions = f.queryset(None, Transcription.objects.all())
        self.assertEqual(transcriptions.count(), 1)
