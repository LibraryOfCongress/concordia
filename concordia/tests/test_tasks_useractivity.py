from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import TestCase

from concordia.exceptions import CacheLockedError
from concordia.models import Transcription
from concordia.tasks.unusualactivity import unusual_activity
from concordia.tasks.useractivity import (
    update_useractivity_cache,
    update_userprofileactivity_from_cache,
)

from .utils import CreateTestUsers, create_campaign


class TaskTestCase(CreateTestUsers, TestCase):
    def setUp(self):
        cache.clear()
        self.user = self.create_test_user()
        self.campaign = create_campaign()
        self.key = f"userprofileactivity_{self.campaign.pk}"

    @mock.patch("concordia.tasks.useractivity.update_userprofileactivity_table")
    def test_update_userprofileactivity_from_cache_no_updates(self, mock_update_table):
        cache.set(self.key, None)
        with mock.patch("concordia.logging.ConcordiaLogger.debug") as mock_debug:
            update_userprofileactivity_from_cache()
            self.assertEqual(mock_debug.call_count, 2)
            mock_debug.assert_called_with(
                "Cache contained no updates for key. Skipping",
                event_code="update_userprofileactivity_from_cache_no_updates",
                key=self.key,
            )
        self.assertEqual(mock_update_table.call_count, 0)

    @mock.patch("concordia.tasks.useractivity.update_userprofileactivity_table")
    def test_update_userprofileactivity_from_cache_update(self, mock_update_table):
        cache.set(self.key, {self.user.pk: (1, 0)})
        update_userprofileactivity_from_cache()
        self.assertEqual(mock_update_table.call_count, 2)
        mock_update_table.assert_has_calls(
            [
                mock.call(self.user, self.campaign.id, "transcribe_count", 1),
                mock.call(self.user, self.campaign.id, "review_count", 0),
            ]
        )
        self.assertIsNone(cache.get(self.key))

    @mock.patch("concordia.tasks.unusualactivity.Transcription.objects")
    def test_unusual_activity(self, mock_transcription):
        mock_transcription.transcribe_incidents.return_value = (
            Transcription.objects.none()
        )
        mock_transcription.review_incidents.return_value = Transcription.objects.none()
        unusual_activity(ignore_env=True)
        self.assertEqual(len(mail.outbox), 1)
        expected_subject = "Unusual User Activity Report"
        self.assertIn(expected_subject, mail.outbox[0].subject)

    @mock.patch("django.core.cache.cache.add")
    @mock.patch("django.core.cache.cache.delete")
    @mock.patch("concordia.tasks.useractivity._update_useractivity_cache")
    def test_update_useractivity_cache(self, mock_update, mock_delete, mock_add):
        user = self.user
        campaign = self.campaign

        mock_add.return_value = False
        with self.assertRaises(CacheLockedError):
            update_useractivity_cache(user.id, campaign.id, "transcribe")
        self.assertEqual(mock_update.call_count, 0)
        self.assertEqual(mock_delete.call_count, 0)

        mock_add.return_value = True
        update_useractivity_cache(user.id, campaign.id, "transcribe")
        self.assertEqual(mock_update.call_count, 1)
        mock_update.assert_called_with(user.id, campaign.id, "transcribe")
        self.assertEqual(mock_delete.call_count, 1)
        mock_delete.assert_called_with("userprofileactivity_cache_lock")

        update_useractivity_cache(user.id, campaign.id, "review")
        self.assertEqual(mock_update.call_count, 2)
        mock_update.assert_called_with(user.id, campaign.id, "review")
        self.assertEqual(mock_delete.call_count, 2)
        mock_delete.assert_called_with("userprofileactivity_cache_lock")


class UpdateUserprofileactivityFromCacheTestCase(CreateTestUsers, TestCase):
    def setUp(self):
        cache.clear()
        self.user = self.create_test_user()
        self.campaign = create_campaign()
        self.key = f"userprofileactivity_{self.campaign.pk}"

    @mock.patch("concordia.tasks.useractivity.update_userprofileactivity_table")
    def test_no_updates(self, mock_update_table):
        cache.set(self.key, None)
        with mock.patch("concordia.logging.ConcordiaLogger.debug") as mock_debug:
            update_userprofileactivity_from_cache()
            self.assertEqual(mock_debug.call_count, 2)
            mock_debug.assert_called_with(
                "Cache contained no updates for key. Skipping",
                event_code="update_userprofileactivity_from_cache_no_updates",
                key=self.key,
            )
        self.assertEqual(mock_update_table.call_count, 0)

    @mock.patch("concordia.tasks.useractivity.update_userprofileactivity_table")
    def test_update(self, mock_update_table):
        cache.set(self.key, {self.user.pk: (1, 0)})
        update_userprofileactivity_from_cache()
        self.assertEqual(mock_update_table.call_count, 2)
        mock_update_table.assert_has_calls(
            [
                mock.call(self.user, self.campaign.id, "transcribe_count", 1),
                mock.call(self.user, self.campaign.id, "review_count", 0),
            ]
        )
        self.assertIsNone(cache.get(self.key))
