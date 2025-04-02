from django.db import models
from django.test import TestCase
from django.utils import timezone

from concordia.documents import (
    AssetDocument,
    TranscriptionDocument,
    UserDocument,
)
from concordia.models import Asset, Transcription
from concordia.tests.utils import CreateTestUsers, create_transcription


class UserDocumentTestCase(CreateTestUsers, TestCase):
    def test_prepare_transcription_count(self):
        doc = UserDocument()
        user = self.create_test_user()
        self.assertEqual(0, doc.prepare_transcription_count(user))

        create_transcription(user=user)
        self.assertEqual(1, doc.prepare_transcription_count(user))


class AssetDocumentTestCase(TestCase):
    def test_get_queryset(self):
        qs = AssetDocument().get_queryset()
        self.assertIsInstance(qs, models.QuerySet)
        self.assertEqual(qs.model, Asset)


class TagCollectionDocumentTestCase(TestCase):
    def test_get_queryset(self):
        qs = TranscriptionDocument().get_queryset()
        self.assertIsInstance(qs, models.QuerySet)
        self.assertEqual(qs.model, Transcription)


class TranscriptionDocumentTestCase(TestCase):
    def test_prepare_submission_count(self):
        doc = AssetDocument()
        transcription = create_transcription()
        self.assertEqual(1, doc.prepare_submission_count(transcription.asset))

        transcription.submitted = timezone.now()
        transcription.save()
        self.assertEqual(0, doc.prepare_submission_count(transcription.asset))

    def test_get_queryset(self):
        qs = TranscriptionDocument().get_queryset()
        self.assertIsInstance(qs, models.QuerySet)
        self.assertEqual(qs.model, Transcription)
