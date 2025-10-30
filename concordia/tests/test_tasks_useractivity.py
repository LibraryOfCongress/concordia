from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import TestCase

from concordia.exceptions import CacheLockedError
from concordia.models import Campaign, Transcription, UserProfileActivity
from concordia.tasks.unusualactivity import unusual_activity
from concordia.tasks.useractivity import (
    populate_active_campaign_counts,
    populate_completed_campaign_counts,
    update_useractivity_cache,
    update_userprofileactivity_from_cache,
)
from concordia.utils import get_anonymous_user

from .utils import (
    CreateTestUsers,
    create_asset,
    create_campaign,
    create_item,
    create_project,
    create_tag,
    create_tag_collection,
    create_transcription,
)


class UserActivityTaskTestCase(CreateTestUsers, TestCase):
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

    def test_populate_active_campaign_counts_computes_user_and_anon_rows(self):
        camp = create_campaign(slug="ua-camp-a")
        proj = create_project(campaign=camp, slug="ua-proj-a")
        item = create_item(project=proj, item_id="ua-item-a")
        a1 = create_asset(item=item, slug="ua-a1", sequence=1)
        a2 = create_asset(item=item, slug="ua-a2", sequence=2)

        u1 = self.create_test_user("ua-u1")
        u2 = self.create_test_user("ua-u2")
        anon = get_anonymous_user()

        create_transcription(asset=a1, user=u1, reviewed_by=u2)
        create_transcription(asset=a2, user=u2, reviewed_by=u1)
        create_transcription(asset=a1, user=anon)
        create_transcription(asset=a2, user=u2, reviewed_by=anon)

        t1 = create_tag(value="ua-t1")
        t2 = create_tag(value="ua-t2")
        create_tag_collection(tag=t1, asset=a1, user=u1)
        create_tag_collection(tag=t2, asset=a2, user=u1)
        create_tag_collection(tag=t1, asset=a2, user=anon)

        populate_active_campaign_counts.run()

        rows = UserProfileActivity.objects.filter(campaign=camp)
        self.assertEqual(rows.count(), 3)

        r_u1 = rows.get(user=u1)
        r_u2 = rows.get(user=u2)
        r_an = rows.get(user=anon)

        self.assertEqual(r_u1.asset_count, 2)
        self.assertEqual(r_u1.asset_tag_count, 2)
        self.assertEqual(r_u1.transcribe_count, 1)
        self.assertEqual(r_u1.review_count, 1)

        self.assertEqual(r_u2.asset_count, 2)
        self.assertEqual(r_u2.asset_tag_count, 0)
        self.assertEqual(r_u2.transcribe_count, 2)
        self.assertEqual(r_u2.review_count, 1)

        self.assertEqual(r_an.asset_count, 2)
        self.assertEqual(r_an.asset_tag_count, 1)
        self.assertEqual(r_an.transcribe_count, 1)
        self.assertEqual(r_an.review_count, 1)

    def test_populate_completed_campaign_counts_processes_non_active_only(self):
        active = create_campaign(slug="ua-act-1")
        p1 = create_project(campaign=active, slug="ua-act-proj")
        it1 = create_item(project=p1, item_id="ua-act-item")
        a_act = create_asset(item=it1, slug="ua-act-a")
        u_act = self.create_test_user("ua-act-u")
        create_transcription(asset=a_act, user=u_act)

        retired = create_campaign(slug="ua-ret-1", status=Campaign.Status.RETIRED)
        p2 = create_project(campaign=retired, slug="ua-ret-proj")
        it2 = create_item(project=p2, item_id="ua-ret-item")
        a_ret = create_asset(item=it2, slug="ua-ret-a")
        u_ret = self.create_test_user("ua-ret-u")
        create_transcription(asset=a_ret, user=u_ret)

        populate_completed_campaign_counts.run()

        self.assertFalse(UserProfileActivity.objects.filter(campaign=active).exists())
        self.assertTrue(UserProfileActivity.objects.filter(campaign=retired).exists())

    def test_update_useractivity_cache_lock_max_retries_sends_email(self):
        with (
            mock.patch("django.core.cache.cache.add", return_value=False),
            mock.patch.object(update_useractivity_cache, "max_retries", 0, create=True),
            mock.patch("concordia.tasks.useractivity.send_mail") as m_send,
            mock.patch("concordia.logging.ConcordiaLogger.warning") as m_warn,
            mock.patch("concordia.logging.ConcordiaLogger.exception") as m_exc,
            mock.patch("concordia.tasks.useractivity.logger.error") as m_err,
        ):
            with self.assertRaises(CacheLockedError):
                update_useractivity_cache.run(
                    self.user.id, self.campaign.id, "transcribe"
                )

        # Structured logs were emitted
        self.assertTrue(m_warn.called)
        self.assertTrue(m_exc.called)

        # Email sent with expected subject
        self.assertTrue(m_send.called)
        sent_args, sent_kwargs = m_send.call_args
        self.assertEqual(
            sent_args[0],
            "Task update_useractivity_cache failed: cache is locked.",
        )
        # Unstructured error log emitted
        self.assertTrue(m_err.called)

    def test_update_useractivity_cache_update_exception_releases_lock(self):
        with (
            mock.patch("concordia.tasks.useractivity.cache.add", return_value=True),
            mock.patch("concordia.tasks.useractivity.cache.delete") as m_del,
            mock.patch(
                "concordia.tasks.useractivity._update_useractivity_cache",
                side_effect=RuntimeError("boom"),
            ),
            mock.patch("concordia.tasks.useractivity.send_mail") as m_mail,
        ):
            with self.assertRaises(RuntimeError):
                update_useractivity_cache.run(self.user.id, self.campaign.id, "review")

        m_del.assert_called_once_with("userprofileactivity_cache_lock")
        m_mail.assert_not_called()


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
