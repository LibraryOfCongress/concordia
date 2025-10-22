from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest import mock

from django.core import mail
from django.core.cache import cache, caches
from django.test import TestCase, override_settings
from django.utils import timezone
from requests.models import Response

from concordia.exceptions import CacheLockedError
from concordia.models import (
    Campaign,
    KeyMetricsReport,
    NextReviewableCampaignAsset,
    NextReviewableTopicAsset,
    NextTranscribableCampaignAsset,
    NextTranscribableTopicAsset,
    SiteReport,
    Topic,
    Transcription,
    TranscriptionStatus,
)
from concordia.tasks.blogs import fetch_and_cache_blog_images
from concordia.tasks.next_asset.renew import renew_next_asset_cache
from concordia.tasks.next_asset.reviewable import (
    clean_next_reviewable_for_campaign,
    clean_next_reviewable_for_topic,
    populate_next_reviewable_for_campaign,
    populate_next_reviewable_for_topic,
)
from concordia.tasks.next_asset.transcribable import (
    clean_next_transcribable_for_campaign,
    clean_next_transcribable_for_topic,
    populate_next_transcribable_for_campaign,
    populate_next_transcribable_for_topic,
)
from concordia.tasks.reports.backfill import backfill_assets_started_for_site_reports
from concordia.tasks.reports.key_metrics import build_key_metrics_reports
from concordia.tasks.reports.sitereport import (
    _daily_active_users,
    campaign_report,
    site_report,
)
from concordia.tasks.unusualactivity import unusual_activity
from concordia.tasks.useractivity import (
    update_useractivity_cache,
    update_userprofileactivity_from_cache,
)
from concordia.tasks.visualizations import (
    populate_asset_status_visualization_cache,
    populate_daily_activity_visualization_cache,
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
    create_topic,
    create_transcription,
)


class SiteReportTestCase(CreateTestUsers, TestCase):
    @classmethod
    def setUpTestData(cls):
        # We use setUpTestData instead of setUp so the database is only set
        # up once rather than for each individual test in this test case
        cls.user1 = cls.create_user(username="tester1")
        cls.user2 = cls.create_user(username="tester2")
        cls.user3 = cls.create_user(username="tester3")
        cls.anonymous_user = get_anonymous_user()
        cls.asset1 = create_asset()
        cls.item1 = cls.asset1.item
        cls.project1 = cls.item1.project
        cls.campaign1 = cls.project1.campaign
        cls.asset1_transcription1 = create_transcription(
            asset=cls.asset1, user=cls.user1, accepted=timezone.now()
        )
        cls.asset1_transcription2 = create_transcription(
            asset=cls.asset1,
            user=cls.anonymous_user,
            rejected=timezone.now(),
            reviewed_by=cls.user1,
        )
        cls.topic1 = create_topic(project=cls.project1)
        cls.tag1 = create_tag()
        cls.tag_collection1 = create_tag_collection(
            tag=cls.tag1, asset=cls.asset1, user=cls.user1
        )

        cls.campaign2 = create_campaign(slug="test-campaign-slug-2")
        cls.project2 = create_project(
            campaign=cls.campaign2, slug="test-project-slug-2"
        )
        cls.item2 = create_item(project=cls.project2, item_id="2")
        cls.asset2 = create_asset(item=cls.item2, slug="test-asset-slug-2")
        cls.topic2 = create_topic(
            project=cls.asset2.item.project, slug="test-topic-slug-2"
        )
        cls.tag_collection2 = create_tag_collection(
            tag=cls.tag1, asset=cls.asset2, user=cls.user1
        )

        cls.campaign3 = create_campaign(slug="test-campaign-slug-3")
        cls.project3 = create_project(
            campaign=cls.campaign3, slug="test-project-slug-3"
        )
        cls.item3 = create_item(project=cls.project3, item_id="3")
        cls.asset3 = create_asset(item=cls.item3, slug="test-asset-slug-3")
        cls.asset4 = create_asset(
            item=cls.item3, slug="test-asset-slug-4", published=False
        )
        cls.item4 = create_item(project=cls.project3, item_id="4", published=False)
        cls.asset5 = create_asset(
            item=cls.item4, slug="test-asset-slug-5", published=False
        )

        cls.project3.topics.add(cls.topic1)
        cls.project3.topics.add(cls.topic2)

        cls.retired_campaign = create_campaign(slug="retired-campaign-slug")
        cls.retired_project = create_project(
            campaign=cls.retired_campaign, slug="retired-project-slug"
        )
        cls.retired_item = create_item(project=cls.retired_project)
        cls.retired_asset = create_asset(
            item=cls.retired_item, slug="retired-asset-slug"
        )
        time = timezone.now() - timedelta(days=1, hours=1)
        cls.retired_asset_transcription1 = create_transcription(
            asset=cls.retired_asset, user=cls.user1, accepted=time
        )
        # Done like this to override auto_now_add and auto_now
        Transcription.objects.filter(pk=cls.retired_asset_transcription1.pk).update(
            created_on=time, updated_on=time
        )
        time = timezone.now() - timedelta(days=1, seconds=1)
        cls.retired_asset_transcription2 = create_transcription(
            asset=cls.retired_asset,
            user=cls.user2,
            rejected=time,
            reviewed_by=cls.user1,
        )
        # Done like this to override auto_now_add and auto_now
        Transcription.objects.filter(pk=cls.retired_asset_transcription2.pk).update(
            created_on=time, updated_on=time
        )

        # Generate the campaign report before "retiring" the campaign to populate
        # the retired total report
        cls.retired_campaign_report = campaign_report(campaign=cls.retired_campaign)
        cls.retired_asset.delete()
        cls.retired_item.delete()
        cls.retired_project.delete()
        cls.retired_campaign.status = Campaign.Status.RETIRED
        cls.retired_campaign.save()

        site_report()
        cls.site_report = SiteReport.objects.filter(
            report_name=SiteReport.ReportName.TOTAL
        ).first()
        cls.retired_site_report = SiteReport.objects.filter(
            report_name=SiteReport.ReportName.RETIRED_TOTAL
        ).first()
        cls.campaign1_report = SiteReport.objects.filter(campaign=cls.campaign1).first()
        cls.topic1_report = SiteReport.objects.filter(topic=cls.topic1).first()

    def test_daily_active_users(self):
        self.assertEqual(_daily_active_users(), 2)

    def test_site_report(self):
        self.assertEqual(self.site_report.assets_total, 5)
        self.assertEqual(self.site_report.assets_published, 3)
        self.assertEqual(self.site_report.assets_not_started, 4)
        self.assertEqual(self.site_report.assets_in_progress, 1)
        self.assertEqual(self.site_report.assets_waiting_review, 0)
        self.assertEqual(self.site_report.assets_completed, 0)
        self.assertEqual(self.site_report.assets_unpublished, 2)
        self.assertEqual(self.site_report.items_published, 3)
        self.assertEqual(self.site_report.items_unpublished, 1)
        self.assertEqual(self.site_report.projects_published, 3)
        self.assertEqual(self.site_report.projects_unpublished, 0)
        self.assertEqual(self.site_report.anonymous_transcriptions, 1)
        self.assertEqual(self.site_report.transcriptions_saved, 2)
        self.assertEqual(self.site_report.daily_review_actions, 2)
        self.assertEqual(self.site_report.distinct_tags, 1)
        self.assertEqual(self.site_report.tag_uses, 2)
        self.assertEqual(self.site_report.campaigns_published, 4)
        self.assertEqual(self.site_report.campaigns_unpublished, 0)
        self.assertEqual(self.site_report.users_registered, 4)
        self.assertEqual(self.site_report.users_activated, 4)
        self.assertEqual(self.site_report.daily_active_users, 2)

    def test_retired_site_report(self):
        self.assertEqual(self.retired_site_report.assets_total, 1)
        self.assertEqual(self.retired_site_report.assets_published, 1)
        self.assertEqual(self.retired_site_report.assets_not_started, 0)
        self.assertEqual(self.retired_site_report.assets_in_progress, 1)
        self.assertEqual(self.retired_site_report.assets_waiting_review, 0)
        self.assertEqual(self.retired_site_report.assets_completed, 0)
        self.assertEqual(self.retired_site_report.assets_unpublished, 0)
        self.assertEqual(self.retired_site_report.items_published, 1)
        self.assertEqual(self.retired_site_report.items_unpublished, 0)
        self.assertEqual(self.retired_site_report.projects_published, 1)
        self.assertEqual(self.retired_site_report.projects_unpublished, 0)
        self.assertEqual(self.retired_site_report.anonymous_transcriptions, 0)
        self.assertEqual(self.retired_site_report.transcriptions_saved, 2)
        self.assertEqual(self.retired_site_report.daily_review_actions, 0)
        self.assertEqual(self.retired_site_report.distinct_tags, 0)
        self.assertEqual(self.retired_site_report.tag_uses, 0)
        self.assertEqual(self.retired_site_report.registered_contributors, 2)

    def test_campaign_report(self):
        self.assertEqual(self.campaign1_report.assets_total, 1)
        self.assertEqual(self.campaign1_report.assets_published, 1)
        self.assertEqual(self.campaign1_report.assets_not_started, 0)
        self.assertEqual(self.campaign1_report.assets_in_progress, 1)
        self.assertEqual(self.campaign1_report.assets_waiting_review, 0)
        self.assertEqual(self.campaign1_report.assets_completed, 0)
        self.assertEqual(self.campaign1_report.assets_unpublished, 0)
        self.assertEqual(self.campaign1_report.items_published, 1)
        self.assertEqual(self.campaign1_report.items_unpublished, 0)
        self.assertEqual(self.campaign1_report.projects_published, 1)
        self.assertEqual(self.campaign1_report.projects_unpublished, 0)
        self.assertEqual(self.campaign1_report.anonymous_transcriptions, 1)
        self.assertEqual(self.campaign1_report.transcriptions_saved, 2)
        self.assertEqual(self.campaign1_report.daily_review_actions, 2)
        self.assertEqual(self.campaign1_report.distinct_tags, 1)
        self.assertEqual(self.campaign1_report.tag_uses, 1)
        self.assertEqual(self.campaign1_report.registered_contributors, 2)

    def test_topic_report(self):
        self.assertEqual(self.topic1_report.assets_total, 4)
        self.assertEqual(self.topic1_report.assets_published, 2)
        self.assertEqual(self.topic1_report.assets_not_started, 3)
        self.assertEqual(self.topic1_report.assets_in_progress, 1)
        self.assertEqual(self.topic1_report.assets_waiting_review, 0)
        self.assertEqual(self.topic1_report.assets_completed, 0)
        self.assertEqual(self.topic1_report.assets_unpublished, 2)
        self.assertEqual(self.topic1_report.items_published, 2)
        self.assertEqual(self.topic1_report.items_unpublished, 1)
        self.assertEqual(self.topic1_report.projects_published, 2)
        self.assertEqual(self.topic1_report.projects_unpublished, 0)
        self.assertEqual(self.topic1_report.anonymous_transcriptions, 1)
        self.assertEqual(self.topic1_report.transcriptions_saved, 2)
        self.assertEqual(self.topic1_report.daily_review_actions, 2)
        self.assertEqual(self.topic1_report.distinct_tags, 1)
        self.assertEqual(self.topic1_report.tag_uses, 1)


class TaskTestCase(CreateTestUsers, TestCase):
    def setUp(self):
        cache.clear()

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
    @mock.patch("concordia.tasks.reports.sitereport._update_useractivity_cache")
    def test_update_useractivity_cache(self, mock_update, mock_delete, mock_add):
        user = self.create_test_user()
        campaign = create_campaign()

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

    @mock.patch("concordia.tasks.blog.extract_og_image")
    @mock.patch("concordia.parser.requests.get")
    def test_fetch_and_cache_blog_images(self, mock_get, mock_extract):
        link1 = "https://blogs.loc.gov/thesignal/2025/05/volunteers-ocr/"
        link2 = "https://blogs.loc.gov/thesignal/2025/02/douglass-day-2025/"
        rss = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <item><link>%s</link></item><item><link>%s</link></item>
          </channel>
        </rss>""" % (
            link1,
            link2,
        )
        mock_response = mock.MagicMock(spec=Response)
        mock_response.content = rss
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        # run the celery task
        fetch_and_cache_blog_images()

        mock_extract.assert_any_call(link1)
        mock_extract.assert_any_call(link2)
        self.assertEqual(mock_extract.call_count, 2)


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


class PopulateNextAssetTasksTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.anon = get_anonymous_user()
        self.user = self.create_test_user()
        self.asset1 = create_asset(slug="test-asset-1", title="Test Asset 1")
        self.asset2 = create_asset(
            item=self.asset1.item, slug="test-asset-2", title="Test Asset 2"
        )
        self.topic = create_topic(project=self.asset1.item.project)
        self.campaign = self.asset1.campaign

    def test_populate_next_transcribable_for_campaign(self):
        populate_next_transcribable_for_campaign(campaign_id=self.campaign.id)
        self.assertEqual(
            NextTranscribableCampaignAsset.objects.filter(
                campaign=self.campaign
            ).count(),
            2,
        )

    def test_populate_next_transcribable_for_topic(self):
        populate_next_transcribable_for_topic(topic_id=self.topic.id)
        self.assertEqual(
            NextTranscribableTopicAsset.objects.filter(topic=self.topic).count(), 2
        )

    def test_populate_next_reviewable_for_campaign(self):
        create_transcription(
            asset=self.asset1, user=self.anon, submitted=timezone.now()
        )
        create_transcription(
            asset=self.asset2, user=self.user, submitted=timezone.now()
        )
        populate_next_reviewable_for_campaign(campaign_id=self.campaign.id)
        self.assertEqual(
            NextReviewableCampaignAsset.objects.filter(campaign=self.campaign).count(),
            2,
        )

    def test_populate_next_reviewable_for_topic(self):
        create_transcription(
            asset=self.asset1, user=self.anon, submitted=timezone.now()
        )
        create_transcription(
            asset=self.asset2, user=self.user, submitted=timezone.now()
        )
        populate_next_reviewable_for_topic(topic_id=self.topic.id)
        self.assertEqual(
            NextReviewableTopicAsset.objects.filter(topic=self.topic).count(), 2
        )

    @mock.patch("concordia.tasks.next_asset.transcribable.logger")
    def test_populate_next_transcribable_for_campaign_missing(self, mock_logger):
        populate_next_transcribable_for_campaign(campaign_id=9999)
        mock_logger.error.assert_called_once()

    @mock.patch("concordia.tasks.next_asset.transcribable.logger")
    def test_populate_next_transcribable_for_topic_missing(self, mock_logger):
        populate_next_transcribable_for_topic(topic_id=9999)
        mock_logger.error.assert_called_once()

    @mock.patch("concordia.tasks.next_asset.reviewable.logger")
    def test_populate_next_reviewable_for_campaign_missing(self, mock_logger):
        populate_next_reviewable_for_campaign(campaign_id=9999)
        mock_logger.error.assert_called_once()

    @mock.patch("concordia.tasks.next_asset.reviewable.logger")
    def test_populate_next_reviewable_for_topic_missing(self, mock_logger):
        populate_next_reviewable_for_topic(topic_id=9999)
        mock_logger.error.assert_called_once()

    @mock.patch("concordia.tasks.next_asset.transcribable.logger")
    def test_populate_next_transcribable_for_campaign_none_needed(self, mock_logger):
        for i in range(3, 103):
            asset = create_asset(item=self.asset1.item, slug=f"dummy-{i}")
            NextTranscribableCampaignAsset.objects.create(
                asset=asset,
                item=asset.item,
                item_item_id=asset.item.item_id,
                project=asset.item.project,
                project_slug=asset.item.project.slug,
                campaign=self.campaign,
                sequence=asset.sequence,
                transcription_status=asset.transcription_status,
            )
        populate_next_transcribable_for_campaign(campaign_id=self.campaign.id)
        mock_logger.info.assert_any_call(
            "Campaign %s already has %s next transcribable assets", self.campaign, 100
        )

    @mock.patch("concordia.tasks.next_asset.transcribable.logger")
    def test_populate_next_transcribable_for_topic_none_needed(self, mock_logger):
        for i in range(3, 103):
            asset = create_asset(item=self.asset1.item, slug=f"dummy-{i}")
            NextTranscribableTopicAsset.objects.create(
                asset=asset,
                item=asset.item,
                item_item_id=asset.item.item_id,
                project=asset.item.project,
                project_slug=asset.item.project.slug,
                topic=self.topic,
                sequence=asset.sequence,
                transcription_status=asset.transcription_status,
            )
        populate_next_transcribable_for_topic(topic_id=self.topic.id)
        mock_logger.info.assert_any_call(
            "Topic %s already has %s next transcribable assets", self.topic, 100
        )

    @mock.patch("concordia.tasks.next_asset.reviewable.logger")
    def test_populate_next_reviewable_for_campaign_none_needed(self, mock_logger):
        create_transcription(
            asset=self.asset1, user=self.user, submitted=timezone.now()
        )
        for i in range(3, 103):
            asset = create_asset(item=self.asset1.item, slug=f"r-{i}")
            create_transcription(asset=asset, user=self.user, submitted=timezone.now())
            NextReviewableCampaignAsset.objects.create(
                asset=asset,
                item=asset.item,
                item_item_id=asset.item.item_id,
                project=asset.item.project,
                project_slug=asset.item.project.slug,
                campaign=self.campaign,
                sequence=asset.sequence,
                transcriber_ids=[self.user.id],
            )

        populate_next_reviewable_for_campaign(campaign_id=self.campaign.id)
        mock_logger.info.assert_any_call(
            "Campaign %s already has %s next reviewable assets", self.campaign, 100
        )

    @mock.patch("concordia.tasks.next_asset.reviewable.logger")
    def test_populate_next_reviewable_for_topic_none_needed(self, mock_logger):
        create_transcription(
            asset=self.asset1, user=self.user, submitted=timezone.now()
        )
        for i in range(3, 103):
            asset = create_asset(item=self.asset1.item, slug=f"t-{i}")
            create_transcription(asset=asset, user=self.user, submitted=timezone.now())
            NextReviewableTopicAsset.objects.create(
                asset=asset,
                item=asset.item,
                item_item_id=asset.item.item_id,
                project=asset.item.project,
                project_slug=asset.item.project.slug,
                topic=self.topic,
                sequence=asset.sequence,
                transcriber_ids=[self.user.id],
            )

        populate_next_reviewable_for_topic(topic_id=self.topic.id)
        mock_logger.info.assert_any_call(
            "Topic %s already has %s next reviewable assets", self.topic, 100
        )

    @mock.patch("concordia.tasks.next_asset.reviewable.logger")
    def test_populate_next_reviewable_for_campaign_none_found(self, mock_logger):
        create_transcription(
            asset=self.asset1, user=self.user, submitted=timezone.now()
        )

        NextReviewableCampaignAsset.objects.create(
            asset=self.asset1,
            item=self.asset1.item,
            item_item_id=self.asset1.item.item_id,
            project=self.asset1.item.project,
            project_slug=self.asset1.item.project.slug,
            campaign=self.campaign,
            sequence=self.asset1.sequence,
            transcriber_ids=[self.user.id],
        )

        populate_next_reviewable_for_campaign(campaign_id=self.campaign.id)
        mock_logger.info.assert_any_call(
            "No reviewable assets found in campaign %s", self.campaign
        )

    @mock.patch("concordia.tasks.next_asset.reviewable.logger")
    def test_populate_next_reviewable_for_topic_none_found(self, mock_logger):
        create_transcription(
            asset=self.asset1, user=self.user, submitted=timezone.now()
        )

        NextReviewableTopicAsset.objects.create(
            asset=self.asset1,
            item=self.asset1.item,
            item_item_id=self.asset1.item.item_id,
            project=self.asset1.item.project,
            project_slug=self.asset1.item.project.slug,
            topic=self.topic,
            sequence=self.asset1.sequence,
            transcriber_ids=[self.user.id],
        )

        populate_next_reviewable_for_topic(topic_id=self.topic.id)
        mock_logger.info.assert_any_call(
            "No reviewable assets found in topic %s", self.topic
        )

    @mock.patch("concordia.tasks.next_asset.transcribable.logger")
    def test_populate_next_transcribable_for_campaign_none_found(self, mock_logger):
        for asset in (self.asset1, self.asset2):
            NextTranscribableCampaignAsset.objects.create(
                asset=asset,
                item=asset.item,
                item_item_id=asset.item.item_id,
                project=asset.item.project,
                project_slug=asset.item.project.slug,
                campaign=self.campaign,
                sequence=asset.sequence,
                transcription_status=asset.transcription_status,
            )

        populate_next_transcribable_for_campaign(campaign_id=self.campaign.id)
        mock_logger.info.assert_any_call(
            "No transcribable assets found in campaign %s", self.campaign
        )

    @mock.patch("concordia.tasks.next_asset.transcribable.logger")
    def test_populate_next_transcribable_for_topic_none_found(self, mock_logger):
        for asset in (self.asset1, self.asset2):
            NextTranscribableTopicAsset.objects.create(
                asset=asset,
                item=asset.item,
                item_item_id=asset.item.item_id,
                project=asset.item.project,
                project_slug=asset.item.project.slug,
                topic=self.topic,
                sequence=asset.sequence,
                transcription_status=asset.transcription_status,
            )

        populate_next_transcribable_for_topic(topic_id=self.topic.id)
        mock_logger.info.assert_any_call(
            "No transcribable assets found in topic %s", self.topic
        )


class CleanNextAssetTasksTests(TestCase):
    def setUp(self):
        self.asset = create_asset()
        self.campaign = self.asset.campaign
        self.topic = create_topic(project=self.asset.item.project)
        self.campaign_transcribable = NextTranscribableCampaignAsset.objects.create(
            asset=self.asset,
            item=self.asset.item,
            item_item_id=self.asset.item.item_id,
            project=self.asset.item.project,
            project_slug=self.asset.item.project.slug,
            campaign=self.campaign,
            sequence=self.asset.sequence,
            transcription_status=TranscriptionStatus.NOT_STARTED,
        )
        self.topic_transcribable = NextTranscribableTopicAsset.objects.create(
            asset=self.asset,
            item=self.asset.item,
            item_item_id=self.asset.item.item_id,
            project=self.asset.item.project,
            project_slug=self.asset.item.project.slug,
            topic=self.topic,
            sequence=self.asset.sequence,
            transcription_status=TranscriptionStatus.IN_PROGRESS,
        )
        self.campaign_reviewable = NextReviewableCampaignAsset.objects.create(
            asset=self.asset,
            item=self.asset.item,
            item_item_id=self.asset.item.item_id,
            project=self.asset.item.project,
            project_slug=self.asset.item.project.slug,
            campaign=self.campaign,
            sequence=self.asset.sequence,
        )
        self.topic_reviewable = NextReviewableTopicAsset.objects.create(
            asset=self.asset,
            item=self.asset.item,
            item_item_id=self.asset.item.item_id,
            project=self.asset.item.project,
            project_slug=self.asset.item.project.slug,
            topic=self.topic,
            sequence=self.asset.sequence,
        )

    @mock.patch(
        "concordia.tasks.next_asset.transcribable.populate_next_transcribable_for_campaign.delay"
    )
    def test_clean_next_transcribable_for_campaign(self, mock_delay):
        self.asset.transcription_status = TranscriptionStatus.COMPLETED
        self.asset.save()
        clean_next_transcribable_for_campaign(self.campaign.id)
        self.assertFalse(
            NextTranscribableCampaignAsset.objects.filter(
                campaign=self.campaign
            ).exists()
        )
        mock_delay.assert_called_once_with(self.campaign.id)

    @mock.patch(
        "concordia.tasks.next_asset.transcribable.populate_next_transcribable_for_topic.delay"
    )
    def test_clean_next_transcribable_for_topic(self, mock_delay):
        self.asset.transcription_status = TranscriptionStatus.COMPLETED
        self.asset.save()
        clean_next_transcribable_for_topic(self.topic.id)
        self.assertFalse(
            NextTranscribableTopicAsset.objects.filter(topic=self.topic).exists()
        )
        mock_delay.assert_called_once_with(self.topic.id)

    @mock.patch(
        "concordia.tasks.next_asset.reviewable.populate_next_reviewable_for_campaign.delay"
    )
    def test_clean_next_reviewable_for_campaign(self, mock_delay):
        self.asset.transcription_status = TranscriptionStatus.IN_PROGRESS
        self.asset.save()
        clean_next_reviewable_for_campaign(self.campaign.id)
        self.assertFalse(
            NextReviewableCampaignAsset.objects.filter(campaign=self.campaign).exists()
        )
        mock_delay.assert_called_once_with(self.campaign.id)

    @mock.patch(
        "concordia.tasks.next_asset.reviewable.populate_next_reviewable_for_topic.delay"
    )
    def test_clean_next_reviewable_for_topic(self, mock_delay):
        self.asset.transcription_status = TranscriptionStatus.NOT_STARTED
        self.asset.save()
        clean_next_reviewable_for_topic(self.topic.id)
        self.assertFalse(
            NextReviewableTopicAsset.objects.filter(topic=self.topic).exists()
        )
        mock_delay.assert_called_once_with(self.topic.id)

    @mock.patch(
        "concordia.tasks.next_asset.reviewable.clean_next_reviewable_for_campaign.delay"
    )
    @mock.patch(
        "concordia.tasks.next_asset.transcribable.clean_next_transcribable_for_campaign.delay"
    )
    @mock.patch(
        "concordia.tasks.next_asset.reviewable.clean_next_reviewable_for_topic.delay"
    )
    @mock.patch(
        "concordia.tasks.next_asset.transcribable.clean_next_transcribable_for_topic.delay"
    )
    def test_renew_next_asset_cache(
        self,
        mock_clean_trans_topic,
        mock_clean_rev_topic,
        mock_clean_trans_campaign,
        mock_clean_rev_campaign,
    ):
        renew_next_asset_cache()
        mock_clean_trans_campaign.assert_called_once_with(campaign_id=self.campaign.id)
        mock_clean_rev_campaign.assert_called_once_with(campaign_id=self.campaign.id)
        mock_clean_trans_topic.assert_called_once_with(topic_id=self.topic.id)
        mock_clean_rev_topic.assert_called_once_with(topic_id=self.topic.id)

    @mock.patch("concordia.tasks.next_asset.transcribable.logger")
    def test_clean_next_transcribable_for_campaign_exception(self, mock_logger):
        with mock.patch.object(
            self.campaign_transcribable, "delete", side_effect=Exception("fail")
        ):
            with mock.patch(
                "concordia.tasks.next_asset.transcribable.find_invalid_next_transcribable_campaign_assets",
                return_value=[self.campaign_transcribable],
            ):
                clean_next_transcribable_for_campaign(self.campaign.id)
        mock_logger.exception.assert_called_once()

    @mock.patch("concordia.tasks.next_asset.transcribable.logger")
    def test_clean_next_transcribable_for_topic_exception(self, mock_logger):
        with mock.patch.object(
            self.topic_transcribable, "delete", side_effect=Exception("fail")
        ):
            with mock.patch(
                "concordia.tasks.next_asset.transcribable.find_invalid_next_transcribable_topic_assets",
                return_value=[self.topic_transcribable],
            ):
                clean_next_transcribable_for_topic(self.topic.id)
        mock_logger.exception.assert_called_once()

    @mock.patch("concordia.tasks.next_asset.reviewable.logger")
    def test_clean_next_reviewable_for_campaign_exception(self, mock_logger):
        with mock.patch.object(
            self.campaign_reviewable, "delete", side_effect=Exception("fail")
        ):
            with mock.patch(
                "concordia.tasks.next_asset.reviewable.find_invalid_next_reviewable_campaign_assets",
                return_value=[self.campaign_reviewable],
            ):
                clean_next_reviewable_for_campaign(self.campaign.id)
        mock_logger.exception.assert_called_once()

    @mock.patch("concordia.tasks.next_asset.reviewable.logger")
    def test_clean_next_reviewable_for_topic_exception(self, mock_logger):
        with mock.patch.object(
            self.topic_reviewable, "delete", side_effect=Exception("fail")
        ):
            with mock.patch(
                "concordia.tasks.next_asset.reviewable.find_invalid_next_reviewable_topic_assets",
                return_value=[self.topic_reviewable],
            ):
                clean_next_reviewable_for_topic(self.topic.id)
        mock_logger.exception.assert_called_once()


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        },
        "visualization_cache": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        },
    }
)
class VisualizationCacheTasksTests(TestCase):
    class _UploadFailed(Exception):
        pass

    def setUp(self):
        self.cache = caches["visualization_cache"]
        self.cache.clear()

    def test_populate_asset_status_visualization_cache(self):
        c1 = create_campaign(status=Campaign.Status.ACTIVE, title="Alpha")
        c2 = create_campaign(status=Campaign.Status.ACTIVE, title="Beta")
        p1 = create_project(campaign=c1)
        i1 = create_item(project=p1)
        p2 = create_project(campaign=c2)
        i2 = create_item(project=p2)
        create_asset(item=i1, transcription_status=TranscriptionStatus.NOT_STARTED)
        create_asset(
            item=i2,
            slug="test-asset-2",
            transcription_status=TranscriptionStatus.IN_PROGRESS,
        )
        create_asset(
            item=i2,
            slug="test-asset-3",
            transcription_status=TranscriptionStatus.SUBMITTED,
        )
        create_asset(
            item=i2,
            slug="test-asset-4",
            transcription_status=TranscriptionStatus.COMPLETED,
        )

        populate_asset_status_visualization_cache.run()

        overview = self.cache.get("asset-status-overview")
        expected_labels = [
            TranscriptionStatus.CHOICE_MAP[key]
            for key, _ in TranscriptionStatus.CHOICES
        ]
        self.assertEqual(overview["status_labels"], expected_labels)
        # Totals: 1 not_started, 1 in_progress, 1 submitted, 1 completed
        self.assertEqual(overview["total_counts"], [1, 1, 1, 1])

    def test_populate_daily_activity_visualization_cache(self):
        date1 = (timezone.now() - timedelta(days=2)).date()
        date2 = (timezone.now() - timedelta(days=1)).date()

        sr1 = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            transcriptions_saved=5,
            daily_review_actions=1,
        )
        sr2 = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            transcriptions_saved=10,
            daily_review_actions=2,
        )
        # Set specific created_on dates directly in DB
        SiteReport.objects.filter(pk=sr1.pk).update(created_on=date1)
        SiteReport.objects.filter(pk=sr2.pk).update(created_on=date2)

        populate_daily_activity_visualization_cache.run()

        result = self.cache.get("daily-transcription-activity-last-28-days")
        self.assertIsNotNone(result)

        expected_labels = [(date2 - timedelta(days=1)), date2]
        expected_labels = [d.strftime("%Y-%m-%d") for d in expected_labels]

        # Extract the two datasets
        datasets = result["transcription_datasets"]
        self.assertEqual(len(datasets), 2)
        trans = next(ds for ds in datasets if ds["label"] == "Transcriptions")
        reviews = next(ds for ds in datasets if ds["label"] == "Reviews")

        # transcriptions = 5 on date1, 10 - 5 = 5 on date2
        # reviews = 1 on date1, 2 on date2
        self.assertEqual(trans["data"][-2:], [5, 5])  # last two days in the data range
        self.assertEqual(reviews["data"][-2:], [1, 2])

    def test_negative_daily_saved_clamps_to_zero(self):
        date1 = (timezone.now() - timedelta(days=2)).date()
        date2 = (timezone.now() - timedelta(days=1)).date()

        sr1 = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            transcriptions_saved=10,
            daily_review_actions=0,
        )
        sr2 = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            transcriptions_saved=5,  # decreased total, which should not happen
            daily_review_actions=0,
        )
        SiteReport.objects.filter(pk=sr1.pk).update(created_on=date1)
        SiteReport.objects.filter(pk=sr2.pk).update(created_on=date2)

        populate_daily_activity_visualization_cache.run()

        result = self.cache.get("daily-transcription-activity-last-28-days")
        self.assertIsNotNone(result)

        datasets = result["transcription_datasets"]
        trans = next(ds for ds in datasets if ds["label"] == "Transcriptions")

        # Should clamp the second day to 0
        self.assertEqual(trans["data"][-2:], [10, 0])

    def test_asset_status_unchanged_skips_upload_and_cache_update(self):
        campaign = create_campaign(status=Campaign.Status.ACTIVE, title="Only")
        project = create_project(campaign=campaign)
        item = create_item(project=project)
        create_asset(item=item, transcription_status=TranscriptionStatus.NOT_STARTED)
        create_asset(
            item=item, slug="a2", transcription_status=TranscriptionStatus.IN_PROGRESS
        )
        create_asset(
            item=item, slug="a3", transcription_status=TranscriptionStatus.SUBMITTED
        )
        create_asset(
            item=item, slug="a4", transcription_status=TranscriptionStatus.COMPLETED
        )

        expected_counts = [1, 1, 1, 1]

        existing_payload = {
            "status_labels": [
                TranscriptionStatus.CHOICE_MAP[key]
                for key, _ in TranscriptionStatus.CHOICES
            ],
            "total_counts": expected_counts,
            "csv_url": "https://old.example/asset-status.csv",
        }
        self.cache.set("asset-status-overview", existing_payload, None)

        with (
            mock.patch(
                "concordia.tasks.visualizations.VISUALIZATION_STORAGE.save"
            ) as mock_save,
            mock.patch("concordia.tasks.visualizations.structured_logger") as mock_log,
        ):
            populate_asset_status_visualization_cache.run()

            mock_save.assert_not_called()
            # Cache should remain as-is
            self.assertEqual(self.cache.get("asset-status-overview"), existing_payload)
            # Logged unchanged
            self.assertTrue(mock_log.info.called)
            self.assertEqual(
                mock_log.info.call_args.kwargs.get("event_code"),
                "asset_status_vis_unchanged",
            )

    def test_asset_status_upload_failure_with_prior_url_falls_back(self):
        campaign = create_campaign(status=Campaign.Status.ACTIVE, title="Only")
        project = create_project(campaign=campaign)
        item = create_item(project=project)
        create_asset(item=item, transcription_status=TranscriptionStatus.NOT_STARTED)

        # Ensure "existing" differs so code takes the non-unchanged path
        self.cache.set(
            "asset-status-overview",
            {
                "status_labels": [],
                "total_counts": [0, 0, 0, 0],
                "csv_url": "https://old.example/asset-status.csv",
            },
            None,
        )

        with (
            mock.patch(
                "concordia.tasks.visualizations.VISUALIZATION_STORAGE.save",
                side_effect=self._UploadFailed("test exception"),
            ),
            mock.patch("concordia.tasks.visualizations.structured_logger") as mock_log,
        ):
            # Should not raise because we have a prior CSV URL to fall back to
            populate_asset_status_visualization_cache.run()

            updated = self.cache.get("asset-status-overview")
            # Counts should reflect the new data (1 in NOT_STARTED; others 0)
            expected = [
                1 if key == TranscriptionStatus.NOT_STARTED else 0
                for key, _ in TranscriptionStatus.CHOICES
            ]
            self.assertEqual(updated["total_counts"], expected)
            # URL should remain the old one
            self.assertEqual(updated["csv_url"], "https://old.example/asset-status.csv")

            # Logged exception with the non-missing-url code
            self.assertTrue(mock_log.exception.called)
            self.assertEqual(
                mock_log.exception.call_args.kwargs.get("event_code"),
                "asset_status_vis_csv_error",
            )

    def test_asset_status_upload_failure_without_prior_url_raises(self):
        campaign = create_campaign(status=Campaign.Status.ACTIVE, title="Only")
        project = create_project(campaign=campaign)
        item = create_item(project=project)
        create_asset(item=item, transcription_status=TranscriptionStatus.NOT_STARTED)

        # No existing cache entry, so no prior URL
        with (
            mock.patch(
                "concordia.tasks.visualizations.VISUALIZATION_STORAGE.save",
                side_effect=self._UploadFailed("test exception"),
            ),
            mock.patch("concordia.tasks.visualizations.structured_logger") as mock_log,
        ):
            with self.assertRaises(self._UploadFailed):
                populate_asset_status_visualization_cache.run()

            self.assertTrue(mock_log.exception.called)
            self.assertEqual(
                mock_log.exception.call_args.kwargs.get("event_code"),
                "asset_status_vis_csv_missing_url_error",
            )

    def test_daily_activity_unchanged_skips_upload_and_cache_update(self):
        # With no SiteReports, both series are 28 zeros; pre-populate matching cache
        zeros = [0] * 28
        existing = {
            "labels": [],  # labels do not matter for the dedupe
            "transcription_datasets": [
                {"label": "Transcriptions", "data": zeros},
                {"label": "Reviews", "data": zeros},
            ],
            "csv_url": "https://old.example/daily.csv",
        }
        self.cache.set("daily-transcription-activity-last-28-days", existing, None)

        with (
            mock.patch(
                "concordia.tasks.visualizations.VISUALIZATION_STORAGE.save"
            ) as mock_save,
            mock.patch("concordia.tasks.visualizations.structured_logger") as mock_log,
        ):
            populate_daily_activity_visualization_cache.run()

            mock_save.assert_not_called()
            self.assertEqual(
                self.cache.get("daily-transcription-activity-last-28-days"), existing
            )
            self.assertTrue(mock_log.info.called)
            self.assertEqual(
                mock_log.info.call_args.kwargs.get("event_code"),
                "daily_activity_vis_unchanged",
            )

    def test_daily_activity_upload_failure_with_prior_url_falls_back(self):
        # Build reports so new data will not be all zeros (ensures "changed" path)
        date1 = (timezone.now() - timedelta(days=2)).date()
        date2 = (timezone.now() - timedelta(days=1)).date()
        sr1 = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            transcriptions_saved=3,
            daily_review_actions=1,
        )
        sr2 = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            transcriptions_saved=5,
            daily_review_actions=2,
        )
        SiteReport.objects.filter(pk=sr1.pk).update(created_on=date1)
        SiteReport.objects.filter(pk=sr2.pk).update(created_on=date2)

        # Prior cache with different series and a CSV URL to fall back to
        self.cache.set(
            "daily-transcription-activity-last-28-days",
            {
                "labels": [],
                "transcription_datasets": [
                    {"label": "Transcriptions", "data": [0] * 28},
                    {"label": "Reviews", "data": [0] * 28},
                ],
                "csv_url": "https://old.example/daily.csv",
            },
            None,
        )

        with (
            mock.patch(
                "concordia.tasks.visualizations.VISUALIZATION_STORAGE.save",
                side_effect=self._UploadFailed("test exception"),
            ),
            mock.patch("concordia.tasks.visualizations.structured_logger") as mock_log,
        ):
            # Should not raise because we have a prior CSV URL
            populate_daily_activity_visualization_cache.run()

            updated = self.cache.get("daily-transcription-activity-last-28-days")
            self.assertIsNotNone(updated)
            # Still using the old URL
            self.assertEqual(updated["csv_url"], "https://old.example/daily.csv")
            # Logged exception with the non-missing-url code
            self.assertTrue(mock_log.exception.called)
            self.assertEqual(
                mock_log.exception.call_args.kwargs.get("event_code"),
                "daily_activity_vis_csv_error",
            )

    def test_daily_activity_upload_failure_without_prior_url_raises(self):
        # No existing cache entry -> csv_url is None
        with (
            mock.patch(
                "concordia.tasks.visualizations.VISUALIZATION_STORAGE.save",
                side_effect=self._UploadFailed("test exception"),
            ),
            mock.patch("concordia.tasks.visualizations.structured_logger") as mock_log,
        ):
            with self.assertRaises(self._UploadFailed):
                populate_daily_activity_visualization_cache.run()

            self.assertTrue(mock_log.exception.called)
            self.assertEqual(
                mock_log.exception.call_args.kwargs.get("event_code"),
                "daily_activity_vis_csv_missing_url_error",
            )


class BackfillAssetsStartedTaskTests(TestCase):
    def _dt(self, days_ago):
        return timezone.now() - timezone.timedelta(days=days_ago)

    def test_updates_total_and_skips_existing_by_default(self):
        # Three TOTAL rows in time order. The last is already populated and
        # should be skipped in default mode.
        r1 = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            assets_not_started=100,
            assets_published=10,
            assets_started=None,
        )
        r2 = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            assets_not_started=92,
            assets_published=17,
            assets_started=None,
        )
        r3 = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            assets_not_started=90,
            assets_published=20,
            assets_started=5,
        )
        SiteReport.objects.filter(pk=r1.pk).update(created_on=self._dt(3))
        SiteReport.objects.filter(pk=r2.pk).update(created_on=self._dt(2))
        SiteReport.objects.filter(pk=r3.pk).update(created_on=self._dt(1))

        updated = backfill_assets_started_for_site_reports.run()
        self.assertEqual(updated, 2)

        r1.refresh_from_db()
        r2.refresh_from_db()
        r3.refresh_from_db()
        self.assertEqual(r1.assets_started, 0)
        self.assertEqual(r2.assets_started, 15)
        self.assertEqual(r3.assets_started, 5)

    @mock.patch("concordia.tasks.reports.backfill.structured_logger")
    def test_recompute_when_skip_existing_is_false(self, _log):
        # Build a TOTAL series with two rows. Make the first row have a wrong,
        # non-null assets_started so it should be recomputed even when skip_existing
        # is False. Make the second row have assets_started=None so the outer
        # exists() precheck lets the series be processed.
        now = timezone.now()

        prev = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            assets_not_started=100,
            assets_published=10,
        )
        curr = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL,
            assets_not_started=90,
            assets_published=15,
        )

        # Enforce chronological order for the iterator
        SiteReport.objects.filter(pk=prev.pk).update(created_on=now - timedelta(days=2))
        SiteReport.objects.filter(pk=curr.pk).update(created_on=now - timedelta(days=1))

        # Wrong non-null on first row, null on second to trigger the series
        SiteReport.objects.filter(pk=prev.pk).update(assets_started=5)
        SiteReport.objects.filter(pk=curr.pk).update(assets_started=None)

        # Run with skip_existing False so both rows are eligible for recompute
        updated = backfill_assets_started_for_site_reports.run(skip_existing=False)
        self.assertEqual(updated, 2)

        prev_refreshed = SiteReport.objects.get(pk=prev.pk)
        curr_refreshed = SiteReport.objects.get(pk=curr.pk)
        # First snapshot in series is always 0
        self.assertEqual(prev_refreshed.assets_started, 0)
        self.assertEqual(curr_refreshed.assets_started, 15)

    def test_processes_retired_campaign_and_topic_series(self):
        # One RETIRED_TOTAL row
        rt = SiteReport.objects.create(
            report_name=SiteReport.ReportName.RETIRED_TOTAL,
            assets_not_started=10,
            assets_published=2,
            assets_started=None,
        )
        SiteReport.objects.filter(pk=rt.pk).update(created_on=self._dt(3))

        # One per-campaign row
        camp = Campaign.objects.create(title="C", slug="c")
        cr = SiteReport.objects.create(
            campaign=camp,
            assets_not_started=7,
            assets_published=1,
            assets_started=None,
        )
        SiteReport.objects.filter(pk=cr.pk).update(created_on=self._dt(2))

        # One per-topic row
        topic = Topic.objects.create(title="T", slug="t")
        tr = SiteReport.objects.create(
            topic=topic,
            assets_not_started=5,
            assets_published=0,
            assets_started=None,
        )
        SiteReport.objects.filter(pk=tr.pk).update(created_on=self._dt(1))

        updated = backfill_assets_started_for_site_reports.run()
        # Each single-row series sets assets_started to 0
        self.assertEqual(updated, 3)

        rt.refresh_from_db()
        cr.refresh_from_db()
        tr.refresh_from_db()
        self.assertEqual(rt.assets_started, 0)
        self.assertEqual(cr.assets_started, 0)
        self.assertEqual(tr.assets_started, 0)


class BuildKeyMetricsReportsTaskTests(TestCase):
    def _dt(self, days_ago):
        return timezone.now() - timezone.timedelta(days=days_ago)

    def test_recompute_all_calls_all_upserts(self):
        # Earliest SiteReport in the current month so only one month is walked.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(created_on=self._dt(2))

        # Seed one MONTHLY and one QUARTERLY row so the later stages run.
        today = timezone.localdate()
        fy = KeyMetricsReport.get_fiscal_year_for_date(today)
        fq = KeyMetricsReport.get_fiscal_quarter_for_date(today)

        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=today.replace(day=1),
            period_end=today,
            fiscal_year=fy,
            fiscal_quarter=fq,
            month=today.month,
        )
        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=today.replace(day=1),
            period_end=today,
            fiscal_year=fy,
            fiscal_quarter=fq,
        )

        with (
            mock.patch.object(KeyMetricsReport, "upsert_month") as up_m,
            mock.patch.object(KeyMetricsReport, "upsert_quarter") as up_q,
            mock.patch.object(KeyMetricsReport, "upsert_fiscal_year") as up_y,
        ):
            up_m.return_value = mock.Mock(period_start=None, period_end=None)
            up_q.return_value = mock.Mock(period_start=None, period_end=None)
            up_y.return_value = mock.Mock(period_start=None, period_end=None)

            changed = build_key_metrics_reports.run(recompute_all=True)

        # One month, four quarters, one fiscal year
        self.assertEqual(changed, 6)
        self.assertEqual(up_m.call_count, 1)
        self.assertEqual(up_q.call_count, 4)
        self.assertEqual(up_y.call_count, 1)

    def test_incremental_refresh_and_creates(self):
        # Make one SiteReport this month so the month is considered.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(created_on=self._dt(2))

        today = timezone.localdate()
        fy = KeyMetricsReport.get_fiscal_year_for_date(today)
        fq = KeyMetricsReport.get_fiscal_quarter_for_date(today)

        # Existing MONTHLY row with old updated_on so it is refreshed.
        monthly = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=today.replace(day=1),
            period_end=today,
            fiscal_year=fy,
            fiscal_quarter=fq,
            month=today.month,
        )
        KeyMetricsReport.objects.filter(pk=monthly.pk).update(updated_on=self._dt(5))

        # Existing QUARTERLY row for the same quarter with older updated_on,
        # so it should be refreshed. The other three quarters are missing and
        # will be created.
        quarter = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=today.replace(day=1),
            period_end=today,
            fiscal_year=fy,
            fiscal_quarter=fq,
        )
        KeyMetricsReport.objects.filter(pk=quarter.pk).update(updated_on=self._dt(5))

        # No FY row yet so it will be created in the FY stage.
        with (
            mock.patch.object(KeyMetricsReport, "upsert_month") as up_m,
            mock.patch.object(KeyMetricsReport, "upsert_quarter") as up_q,
            mock.patch.object(KeyMetricsReport, "upsert_fiscal_year") as up_y,
        ):
            up_m.return_value = mock.Mock(period_start=None, period_end=None)
            up_q.return_value = mock.Mock(period_start=None, period_end=None)
            up_y.return_value = mock.Mock(period_start=None, period_end=None)

            changed = build_key_metrics_reports.run(recompute_all=False)

        # One monthly refresh, three quarterly creates (no refresh since the mock
        # does not bump monthly.updated_on), and one fiscal year create.
        self.assertEqual(changed, 5)
        self.assertEqual(up_m.call_count, 1)
        self.assertEqual(up_q.call_count, 3)
        self.assertEqual(up_y.call_count, 1)

    @mock.patch("concordia.tasks.reports.key_metrics.structured_logger")
    @mock.patch("concordia.tasks.reports.sitereport.SiteReport")
    @mock.patch("concordia.tasks.timezone.localdate")
    def test_early_return_after_backsteps(self, mock_local, mock_sr, slog):
        # Force "today" to mid-March so last_month_start starts at Mar 1.
        mock_local.return_value = date(2024, 3, 15)

        # Earliest SR is mid-December so first_month_start is Dec 1.
        earliest = SimpleNamespace(
            created_on=timezone.make_aware(datetime(2023, 12, 15, 12, 0, 0))
        )
        mock_sr.objects.order_by.return_value.first.return_value = earliest

        # Pretend there are no snapshots by EOM for any month we check.
        mock_sr.objects.filter.return_value.exists.return_value = False

        changed = build_key_metrics_reports.run(recompute_all=False)
        self.assertEqual(changed, 0)

        # Ensure we logged the "no months" message.
        codes = [kw.get("event_code") for _, kw in slog.info.call_args_list if kw]
        self.assertIn("key_metrics_build_no_months", codes)

    @mock.patch("concordia.tasks.report.key_metrics.structured_logger")
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.report.key_metrics.timezone.localdate")
    def test_recompute_all_month_upsert_and_december_rollover(
        self, mock_local, upsert_month, slog
    ):
        # Make yesterday in December so the month we process is December.
        mock_local.return_value = date(2023, 12, 20)

        # Create a TOTAL snapshot in December so the scan does not early-return.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2023, 12, 15, 10, 0, 0))
        )

        # Return a stub report so the "upserted" logging runs.
        upsert_month.return_value = SimpleNamespace(
            period_start=date(2023, 12, 1),
            period_end=date(2023, 12, 31),
        )

        changed = build_key_metrics_reports.run(recompute_all=True)
        self.assertGreaterEqual(changed, 1)

        codes = [kw.get("event_code") for _, kw in slog.info.call_args_list if kw]
        self.assertIn("key_metrics_month_upserted", codes)

    @mock.patch("concordia.tasks.report.key_metrics.structured_logger")
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_fiscal_year"
    )
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.report.key_metrics.timezone.localdate")
    def test_incremental_month_create_and_refresh(
        self,
        mock_local,
        upsert_month,
        upsert_year,
        upsert_quarter,
        slog,
    ):
        mock_local.return_value = date(2024, 2, 1)

        sr_jan = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr_jan.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 10, 9, 0, 0))
        )
        sr_dec = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr_dec.pk).update(
            created_on=timezone.make_aware(datetime(2023, 12, 20, 9, 0, 0))
        )

        dec_month = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=date(2023, 12, 1),
            period_end=date(2023, 12, 31),
            fiscal_year=2024,
            fiscal_quarter=1,
            month=12,
        )
        KeyMetricsReport.objects.filter(pk=dec_month.pk).update(
            updated_on=timezone.make_aware(datetime(2023, 12, 1, 0, 0, 0))
        )

        # Monthly upsert produces a stub (so it counts as 1 change per call)
        upsert_month.return_value = SimpleNamespace(
            period_start=date(2024, 1, 1), period_end=date(2024, 1, 31)
        )
        # Disable quarterly and fiscal-year increments
        upsert_quarter.return_value = None
        upsert_year.return_value = None

        changed = build_key_metrics_reports.run(recompute_all=False)
        self.assertEqual(changed, 2)

    @mock.patch("concordia.tasks.report.key_metrics.structured_logger")
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.objects")
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.report.key_metrics.timezone.localdate")
    def test_quarter_recompute_all_logs(
        self, mock_local, upsert_month, upsert_quarter, kmr_objects, slog
    ):
        mock_local.return_value = date(2024, 1, 15)

        # Ensure we do not early-return (one SR anywhere is fine).
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 1, 8, 0, 0))
        )

        # We are not using monthly upserts here.
        upsert_month.return_value = None

        # monthly_rows -> one fiscal year (2024)
        kmr_objects.filter.return_value.values.return_value.annotate.return_value = [
            {"fiscal_year": 2024}
        ]
        # quarter_exists .first() can be anything; ignored in recompute_all.
        kmr_objects.filter.return_value.first.return_value = None
        # Prevent FY stage from running by returning no quarter years later.
        kmr_objects.filter.return_value.values_list.return_value = []

        upsert_quarter.return_value = SimpleNamespace(
            period_start=date(2024, 1, 1), period_end=date(2024, 3, 31)
        )

        changed = build_key_metrics_reports.run(recompute_all=True)
        # Four quarters upserted
        self.assertGreaterEqual(changed, 4)
        self.assertEqual(upsert_quarter.call_count, 4)

        codes = [kw.get("event_code") for _, kw in slog.info.call_args_list if kw]
        self.assertIn("key_metrics_quarter_upserted", codes)

    @mock.patch("concordia.tasks.report.key_metrics.structured_logger")
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.objects")
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.report.key_metrics.timezone.localdate")
    def test_quarter_incremental_refresh_all_quarters(
        self, mock_local, upsert_month, kmr_objects, upsert_quarter, slog
    ):
        mock_local.return_value = date(2024, 6, 15)

        # Ensure we do not early-return.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 5, 10, 8, 0, 0))
        )

        # No monthly creation in this test.
        upsert_month.return_value = None

        # Signal that we have monthly rows for fiscal_year=2024.
        kmr_objects.filter.return_value.values.return_value.annotate.return_value = [
            {"fiscal_year": 2024}
        ]

        # quarter_exists present for all four quarters.
        quarter_stub = SimpleNamespace(
            updated_on=timezone.make_aware(datetime(2024, 1, 1, 0, 0, 0))
        )

        def filter_side_effect(*args, **kwargs):
            # For QUARTERLY lookups with fiscal_quarter, return an object
            # whose first() yields a stub so "refresh" path is taken.
            class QS:
                def __init__(self, exists_value=False):
                    self._exists = exists_value

                def first(self):
                    return quarter_stub

                def exists(self):
                    return self._exists

                def values(self, *a, **k):
                    return self

                def annotate(self, *a, **k):
                    return [{"fiscal_year": 2024}]

                def values_list(self, *a, **k):
                    # Avoid FY stage in this test
                    return []

            pt = kwargs.get("period_type")
            if pt == KeyMetricsReport.PeriodType.MONTHLY and "updated_on__gt" in kwargs:
                # Make monthly_newer_exists True
                return QS(exists_value=True)
            return QS()

        kmr_objects.filter.side_effect = filter_side_effect

        upsert_quarter.return_value = SimpleNamespace(
            period_start=date(2024, 4, 1), period_end=date(2024, 6, 30)
        )

        changed = build_key_metrics_reports.run(recompute_all=False)
        # Four refreshes (Q1..Q4)
        self.assertGreaterEqual(changed, 4)
        self.assertEqual(upsert_quarter.call_count, 4)

        codes = [kw.get("event_code") for _, kw in slog.info.call_args_list if kw]
        self.assertIn("key_metrics_quarter_refreshed", codes)

    @mock.patch("concordia.tasks.report.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_fiscal_year"
    )
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.objects")
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.report.key_metrics.timezone.localdate")
    def test_fiscal_year_recompute_all_logs(
        self, mock_local, upsert_month, kmr_objects, upsert_year, slog
    ):
        mock_local.return_value = date(2024, 1, 15)

        # Ensure no early-return.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 2, 8, 0, 0))
        )

        upsert_month.return_value = None

        # No monthlies needed; quarters present for FY 2027.
        kmr_objects.filter.return_value.values.return_value.annotate.return_value = []
        kmr_objects.filter.return_value.values_list.return_value = [2027]
        kmr_objects.filter.return_value.first.return_value = None

        upsert_year.return_value = SimpleNamespace(
            period_start=date(2026, 10, 1), period_end=date(2027, 9, 30)
        )

        changed = build_key_metrics_reports.run(recompute_all=True)
        self.assertGreaterEqual(changed, 1)

        codes = [kw.get("event_code") for _, kw in slog.info.call_args_list if kw]
        self.assertIn("key_metrics_year_upserted", codes)

    @mock.patch("concordia.tasks.report.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_fiscal_year"
    )
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.objects")
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.report.key_metrics.timezone.localdate")
    def test_fiscal_year_incremental_create_and_refresh(
        self, mock_local, upsert_month, kmr_objects, upsert_year, slog
    ):
        mock_local.return_value = date(2024, 5, 1)

        # Ensure no early-return.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 4, 15, 8, 0, 0))
        )
        upsert_month.return_value = None

        # First, drive "create" path: quarters exist, FY row is missing.
        def filter_values_list_side_effect(*args, **kwargs):
            # This handles the "fiscal_years_with_quarters" query.
            class QS:
                def values_list(self, *a, **k):
                    return [2026]

                def first(self):
                    return None

                def values(self, *a, **k):
                    return self

                def annotate(self, *a, **k):
                    return []

                def exists(self):
                    return False

            return QS()

        kmr_objects.filter.side_effect = filter_values_list_side_effect

        upsert_year.return_value = SimpleNamespace(
            period_start=date(2025, 10, 1), period_end=date(2026, 9, 30)
        )

        changed1 = build_key_metrics_reports.run(recompute_all=False)
        self.assertGreaterEqual(changed1, 1)
        codes1 = [kw.get("event_code") for _, kw in slog.info.call_args_list if kw]
        self.assertIn("key_metrics_year_created", codes1)

        # Now drive "refresh" path: FY exists, a newer quarter exists.
        fy_stub = SimpleNamespace(
            updated_on=timezone.make_aware(datetime(2024, 3, 1, 0, 0, 0))
        )

        def filter_refresh_side_effect(*args, **kwargs):
            class QS:
                def __init__(self, pt=None):
                    self.pt = pt

                def values_list(self, *a, **k):
                    return [2026]

                def first(self):
                    # When asking for the FY row, return a stub
                    return fy_stub

                def values(self, *a, **k):
                    return self

                def annotate(self, *a, **k):
                    return []

                def exists(self):
                    # This is called for quarters newer than FY.updated_on
                    return True

            return QS()

        kmr_objects.filter.side_effect = filter_refresh_side_effect

        upsert_year.return_value = SimpleNamespace(
            period_start=date(2025, 10, 1), period_end=date(2026, 9, 30)
        )

        changed2 = build_key_metrics_reports.run(recompute_all=False)
        self.assertGreaterEqual(changed2, 1)
        codes2 = [kw.get("event_code") for _, kw in slog.info.call_args_list if kw]
        self.assertIn("key_metrics_year_refreshed", codes2)

    @mock.patch("concordia.tasks.report.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_fiscal_year"
    )
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.report.key_metrics.timezone.localdate")
    def test_recompute_all_quarter_upserts_only(
        self, mock_local, mock_month, mock_quarter, mock_year, slog
    ):
        mock_local.return_value = date(2024, 2, 1)

        # Seed one site snapshot so the task has a start month (Jan 2024).
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 10, 9, 0, 0))
        )

        # Seed a MONTHLY row so the quarter loop sees FY 2024 in the set.
        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
            month=1,
        )

        # Monthly does nothing; quarter upserts return a stub; FY does nothing.
        mock_month.return_value = None
        mock_year.return_value = None

        def quarter_stub(**kwargs):
            return SimpleNamespace(
                period_start=date(2024, 1, 1), period_end=date(2024, 3, 31)
            )

        mock_quarter.side_effect = quarter_stub

        changed = build_key_metrics_reports.run(recompute_all=True)

        # Only quarters (4) should have counted.
        self.assertEqual(changed, 4)
        # Called once per quarter
        self.assertEqual(mock_quarter.call_count, 4)

    @mock.patch("concordia.tasks.report.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_fiscal_year"
    )
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.report.key_metrics.timezone.localdate")
    def test_incremental_quarter_refresh_only(
        self, mock_local, mock_month, mock_quarter, mock_year, slog
    ):
        mock_local.return_value = date(2024, 4, 1)

        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 10, 9, 0, 0))
        )

        # Monthlies for Q2; newer than the quarter row we will refresh
        for m in (1, 2, 3):
            mr = KeyMetricsReport.objects.create(
                period_type=KeyMetricsReport.PeriodType.MONTHLY,
                period_start=date(2024, m, 1),
                period_end=KeyMetricsReport.month_bounds(date(2024, m, 15))[1],
                fiscal_year=2024,
                fiscal_quarter=2,
                month=m,
            )
            KeyMetricsReport.objects.filter(pk=mr.pk).update(
                updated_on=timezone.make_aware(datetime(2024, 3, 31, 12, 0, 0))
            )

        # Pre-create Q1, Q3, Q4 so they are not created by the task
        for fq, ps, pe in [
            (1, date(2023, 10, 1), date(2023, 12, 31)),
            (3, date(2024, 4, 1), date(2024, 6, 30)),
            (4, date(2024, 7, 1), date(2024, 9, 30)),
        ]:
            KeyMetricsReport.objects.create(
                period_type=KeyMetricsReport.PeriodType.QUARTERLY,
                period_start=ps,
                period_end=pe,
                fiscal_year=2024,
                fiscal_quarter=fq,
            )

        # Existing Q2 with older updated_on so only this quarter refreshes
        q2 = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )
        KeyMetricsReport.objects.filter(pk=q2.pk).update(
            updated_on=timezone.make_aware(datetime(2024, 1, 15, 0, 0, 0))
        )

        mock_month.return_value = None
        mock_year.return_value = None
        mock_quarter.return_value = SimpleNamespace(
            period_start=date(2024, 1, 1), period_end=date(2024, 3, 31)
        )

        changed = build_key_metrics_reports.run(recompute_all=False)

        self.assertEqual(changed, 1)
        self.assertEqual(mock_quarter.call_count, 1)

    @mock.patch("concordia.tasks.report.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_fiscal_year"
    )
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.report.key_metrics.timezone.localdate")
    def test_recompute_all_year_upsert_only(
        self, mock_local, mock_month, mock_quarter, mock_year, slog
    ):
        mock_local.return_value = date(2024, 2, 1)

        # Seed snapshot to allow the task to pick a month.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 10, 9, 0, 0))
        )

        # Ensure the 'fiscal_years_with_quarters' set is not empty.
        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )

        # Monthly and quarterly stages do nothing; FY upsert returns a stub.
        mock_month.return_value = None
        mock_quarter.return_value = None
        mock_year.return_value = SimpleNamespace(
            period_start=date(2024, 10, 1), period_end=date(2025, 9, 30)
        )

        changed = build_key_metrics_reports.run(recompute_all=True)

        self.assertEqual(changed, 1)
        self.assertEqual(mock_year.call_count, 1)

    @mock.patch("concordia.tasks.report.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_fiscal_year"
    )
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.report.key_metrics.timezone.localdate")
    def test_incremental_year_create(
        self, mock_local, mock_month, mock_quarter, mock_year, slog
    ):
        mock_local.return_value = date(2024, 2, 1)

        # Seed snapshot and a quarterly row so year loop triggers.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 10, 9, 0, 0))
        )
        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )

        mock_month.return_value = None
        mock_quarter.return_value = None
        mock_year.return_value = SimpleNamespace(
            period_start=date(2024, 10, 1), period_end=date(2025, 9, 30)
        )

        changed = build_key_metrics_reports.run(recompute_all=False)

        self.assertEqual(changed, 1)
        self.assertEqual(mock_year.call_count, 1)

    @mock.patch("concordia.tasks.report.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_fiscal_year"
    )
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.report.key_metrics.timezone.localdate")
    def test_incremental_year_refresh(
        self, mock_local, mock_month, mock_quarter, mock_year, slog
    ):
        mock_local.return_value = date(2024, 4, 1)

        # Seed a quarterly row with new updated_on.
        q = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )
        KeyMetricsReport.objects.filter(pk=q.pk).update(
            updated_on=timezone.make_aware(datetime(2024, 3, 31, 12, 0, 0))
        )

        # Create an older FY row that should be refreshed.
        fy = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.FISCAL_YEAR,
            period_start=date(2023, 10, 1),
            period_end=date(2024, 9, 30),
            fiscal_year=2024,
        )
        KeyMetricsReport.objects.filter(pk=fy.pk).update(
            updated_on=timezone.make_aware(datetime(2024, 1, 1, 0, 0, 0))
        )

        # Need a snapshot so the task can initialize months; it is not used
        # further because we neutralize month and quarter stages.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 10, 9, 0, 0))
        )

        mock_month.return_value = None
        mock_quarter.return_value = None
        mock_year.return_value = SimpleNamespace(
            period_start=date(2023, 10, 1), period_end=date(2024, 9, 30)
        )

        changed = build_key_metrics_reports.run(recompute_all=False)

        self.assertEqual(changed, 1)
        self.assertEqual(mock_year.call_count, 1)

    @mock.patch("concordia.tasks.report.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_fiscal_year"
    )
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.report.key_metrics.timezone.localdate")
    def test_quarter_recompute_all_upserts_and_continue(
        self,
        mock_localdate,
        mock_upsert_month,
        mock_upsert_quarter,
        mock_upsert_year,
        slog,
    ):
        # Make the "monthly" section inert (no changes).
        mock_localdate.return_value = date(2024, 4, 1)
        mock_upsert_month.return_value = None
        mock_upsert_year.return_value = None

        # Seed minimal SiteReport so the monthly stage can compute bounds safely.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 10, 9, 0, 0))
        )

        # Ensure at least one fiscal_year is discovered from MONTHLY rows.
        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
            month=1,
        )

        # Each quarter upsert returns a non-None object so rows_changed increments.
        mock_upsert_quarter.return_value = SimpleNamespace(
            period_start=date(2024, 1, 1), period_end=date(2024, 3, 31)
        )

        changed = build_key_metrics_reports.run(recompute_all=True)

        # Four quarters upserted; monthly and FY upserts return None.
        self.assertEqual(changed, 4)
        self.assertEqual(mock_upsert_quarter.call_count, 4)

    @mock.patch("concordia.tasks.report.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_fiscal_year"
    )
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.report.key_metrics.timezone.localdate")
    def test_fiscal_year_recompute_all_upserts_and_continue(
        self,
        mock_localdate,
        mock_upsert_month,
        mock_upsert_quarter,
        mock_upsert_year,
        slog,
    ):
        mock_localdate.return_value = date(2024, 4, 1)
        mock_upsert_month.return_value = None
        mock_upsert_quarter.return_value = None

        # Seed a quarter so the FY stage finds a fiscal year to process.
        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )

        # Earliest SiteReport so earlier stages do not error.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 5, 9, 0, 0))
        )

        mock_upsert_year.return_value = SimpleNamespace(
            period_start=date(2023, 10, 1), period_end=date(2024, 9, 30)
        )

        changed = build_key_metrics_reports.run(recompute_all=True)

        # Only FY upsert counts (quarter/month upserts return None).
        self.assertEqual(changed, 1)
        self.assertEqual(mock_upsert_year.call_count, 1)

    @mock.patch("concordia.tasks.report.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_fiscal_year"
    )
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.report.key_metrics.timezone.localdate")
    def test_incremental_fiscal_year_created_branch(
        self,
        mock_localdate,
        mock_upsert_month,
        mock_upsert_quarter,
        mock_upsert_year,
        slog,
    ):
        mock_localdate.return_value = date(2024, 4, 1)
        mock_upsert_month.return_value = None
        mock_upsert_quarter.return_value = None

        # Quarter exists for FY discovery; no FY row exists yet.
        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )

        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 2, 9, 0, 0))
        )

        mock_upsert_year.return_value = SimpleNamespace(
            period_start=date(2023, 10, 1), period_end=date(2024, 9, 30)
        )

        changed = build_key_metrics_reports.run(recompute_all=False)

        self.assertEqual(changed, 1)
        self.assertEqual(mock_upsert_year.call_count, 1)

    @mock.patch("concordia.tasks.report.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_fiscal_year"
    )
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_month")
    @mock.patch("concordia.tasks.report.key_metrics.timezone.localdate")
    def test_incremental_fiscal_year_refresh_due_to_newer_quarter(
        self,
        mock_localdate,
        mock_upsert_month,
        mock_upsert_quarter,
        mock_upsert_year,
        slog,
    ):
        mock_localdate.return_value = date(2024, 4, 1)
        mock_upsert_month.return_value = None
        mock_upsert_quarter.return_value = None

        # Existing FY row with earlier updated_on.
        fy = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.FISCAL_YEAR,
            period_start=date(2023, 10, 1),
            period_end=date(2024, 9, 30),
            fiscal_year=2024,
        )
        KeyMetricsReport.objects.filter(pk=fy.pk).update(
            updated_on=timezone.make_aware(datetime(2024, 3, 1, 0, 0, 0))
        )

        # Quarter with newer updated_on to trigger the refresh path.
        q = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )
        KeyMetricsReport.objects.filter(pk=q.pk).update(
            updated_on=timezone.make_aware(datetime(2024, 3, 15, 0, 0, 0))
        )

        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 3, 9, 0, 0))
        )

        mock_upsert_year.return_value = SimpleNamespace(
            period_start=date(2023, 10, 1), period_end=date(2024, 9, 30)
        )

        changed = build_key_metrics_reports.run(recompute_all=False)

        self.assertEqual(changed, 1)
        self.assertEqual(mock_upsert_year.call_count, 1)

    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_month",
        return_value=None,
    )
    @mock.patch("concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_quarter")
    @mock.patch("concordia.tasks.report.key_metrics.timezone.localdate")
    def test_quarter_recompute_all_non_none_continue_edge(
        self, mock_localdate, mock_upsert_quarter, mock_upsert_month
    ):
        mock_localdate.return_value = date(2024, 5, 20)

        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 5, 10, 12, 0, 0))
        )

        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=date(2024, 5, 1),
            period_end=date(2024, 5, 31),
            fiscal_year=2024,
            fiscal_quarter=3,
            month=5,
        )

        dummy = mock.MagicMock(
            period_start=date(2024, 1, 1), period_end=date(2024, 3, 31)
        )
        mock_upsert_quarter.return_value = dummy

        changed = build_key_metrics_reports(recompute_all=True)

        self.assertEqual(changed, 4)
        self.assertEqual(mock_upsert_quarter.call_count, 4)

    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_month",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_quarter",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.KeyMetricsReport.upsert_fiscal_year",
        return_value=mock.MagicMock(
            period_start=date(2024, 10, 1), period_end=date(2025, 9, 30)
        ),
    )
    @mock.patch("concordia.tasks.report.key_metrics.timezone.localdate")
    def test_quarter_incremental_refresh_monthly_newer(
        self,
        mock_localdate,
        mock_upsert_fy,
        mock_upsert_quarter,
        mock_upsert_month,
    ):
        mock_localdate.return_value = date(2024, 1, 20)

        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 10, 9, 0, 0))
        )

        jan = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
            month=1,
        )
        KeyMetricsReport.objects.filter(pk=jan.pk).update(updated_on=timezone.now())

        now = timezone.now()
        older = now - timezone.timedelta(days=10)
        q1 = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2023, 10, 1),
            period_end=date(2023, 12, 31),
            fiscal_year=2024,
            fiscal_quarter=1,
        )
        q2 = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )
        q3 = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 4, 1),
            period_end=date(2024, 6, 30),
            fiscal_year=2024,
            fiscal_quarter=3,
        )
        q4 = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 7, 1),
            period_end=date(2024, 9, 30),
            fiscal_year=2024,
            fiscal_quarter=4,
        )
        KeyMetricsReport.objects.filter(pk=q1.pk).update(updated_on=now)
        KeyMetricsReport.objects.filter(pk=q2.pk).update(updated_on=older)
        KeyMetricsReport.objects.filter(pk=q3.pk).update(updated_on=now)
        KeyMetricsReport.objects.filter(pk=q4.pk).update(updated_on=now)

        fy = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.FISCAL_YEAR,
            period_start=date(2023, 10, 1),
            period_end=date(2024, 9, 30),
            fiscal_year=2024,
        )
        KeyMetricsReport.objects.filter(pk=fy.pk).update(updated_on=now)

        mock_upsert_quarter.return_value = mock.MagicMock(
            period_start=date(2024, 1, 1), period_end=date(2024, 3, 31)
        )

        changed = build_key_metrics_reports.run(recompute_all=False)

        self.assertEqual(changed, 1)
        self.assertGreaterEqual(mock_upsert_quarter.call_count, 1)

    @mock.patch(
        "concordia.tasksreport.key_metrics..KeyMetricsReport.upsert_month",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasksreport.key_metrics..KeyMetricsReport.upsert_quarter",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.KeyMetricsReport.upsert_fiscal_year",
        return_value=mock.MagicMock(
            period_start=date(2024, 10, 1), period_end=date(2025, 9, 30)
        ),
    )
    @mock.patch("concordia.tasks.report.key_metrics.timezone.localdate")
    def test_fiscal_year_recompute_all_non_none_continue_edge(
        self, mock_localdate, mock_upsert_fy, mock_upsert_quarter, mock_upsert_month
    ):
        mock_localdate.return_value = date(2024, 5, 20)

        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 5, 10, 12, 0, 0))
        )

        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )

        changed = build_key_metrics_reports(recompute_all=True)
        self.assertEqual(changed, 1)

    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_month",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_quarter",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.KeyMetricsReport.upsert_fiscal_year",
        return_value=mock.MagicMock(
            period_start=date(2024, 10, 1), period_end=date(2025, 9, 30)
        ),
    )
    @mock.patch("concordia.tasks.report.key_metrics.timezone.localdate")
    def test_fiscal_year_incremental_create_missing(
        self,
        mock_localdate,
        mock_upsert_fy,
        mock_upsert_quarter,
        mock_upsert_month,
    ):
        mock_localdate.return_value = date(2024, 5, 20)

        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        tz = timezone.get_current_timezone()
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 5, 10, 12, 0, 0), tz)
        )

        for qn, start, end in [
            (1, date(2023, 10, 1), date(2023, 12, 31)),
            (2, date(2024, 1, 1), date(2024, 3, 31)),
            (3, date(2024, 4, 1), date(2024, 6, 30)),
            (4, date(2024, 7, 1), date(2024, 9, 30)),
        ]:
            KeyMetricsReport.objects.create(
                period_type=KeyMetricsReport.PeriodType.QUARTERLY,
                period_start=start,
                period_end=end,
                fiscal_year=2024,
                fiscal_quarter=qn,
            )

        changed = build_key_metrics_reports(recompute_all=False)
        self.assertEqual(changed, 1)

    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_month",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_quarter",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_fiscal_year",
        return_value=mock.MagicMock(
            period_start=date(2024, 10, 1), period_end=date(2025, 9, 30)
        ),
    )
    @mock.patch("concordia.tasks.report.key_metrics.timezone.localdate")
    def test_fiscal_year_incremental_refresh_when_quarter_newer(
        self, mock_localdate, mock_upsert_fy, mock_upsert_quarter, mock_upsert_month
    ):
        mock_localdate.return_value = date(2024, 5, 20)

        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 5, 10, 12, 0, 0))
        )

        older = timezone.now() - timezone.timedelta(days=7)
        newer = timezone.now()

        fy = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.FISCAL_YEAR,
            period_start=date(2023, 10, 1),
            period_end=date(2024, 9, 30),
            fiscal_year=2024,
        )
        KeyMetricsReport.objects.filter(pk=fy.pk).update(updated_on=older)

        q2 = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )
        KeyMetricsReport.objects.filter(pk=q2.pk).update(updated_on=newer)

        changed = build_key_metrics_reports(recompute_all=False)
        self.assertEqual(changed, 1)

    @mock.patch("concordia.tasks.report.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_fiscal_year",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_month",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_quarter",
        return_value=None,
    )
    @mock.patch("concordia.tasks.report.key_metrics.timezone.localdate")
    def test_quarter_recompute_all_none_branch_continue(
        self, mock_localdate, upsert_quarter, upsert_month, upsert_year, slog
    ):
        # Keep the monthly scan minimal and stable
        mock_localdate.return_value = date(2024, 2, 10)

        # Seed a site snapshot so the task computes month bounds
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(
                datetime(2024, 2, 9, 12, 0, 0), timezone.get_current_timezone()
            )
        )

        # Ensure the quarterly stage iterates a fiscal year by having a MONTHLY row
        fy = KeyMetricsReport.get_fiscal_year_for_date(mock_localdate.return_value)
        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=date(2024, 2, 1),
            period_end=date(2024, 2, 29),
            fiscal_year=fy,
            fiscal_quarter=2,
            month=2,
        )

        # upsert_quarter returns None -> branch falls through to 'continue'
        changed = build_key_metrics_reports.run(recompute_all=True)

        # No rows changed because monthly and FY are neutralized and quarter
        # upserts return None (hitting the continue path each time).
        self.assertEqual(changed, 0)
        self.assertEqual(upsert_quarter.call_count, 4)

    @mock.patch("concordia.tasks.report.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_fiscal_year",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_month",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_quarter",
        return_value=None,
    )
    @mock.patch("concordia.tasks.report.key_metrics.timezone.localdate")
    def test_quarter_incremental_refresh_none_branch_continue(
        self,
        mock_localdate,
        mock_upsert_quarter,
        mock_upsert_month,
        mock_upsert_year,
        slog,
    ):
        # Ensure monthly scan has a valid window
        mock_localdate.return_value = date(2024, 2, 10)

        # Seed one site snapshot so month range can be computed
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        tz = timezone.get_current_timezone()
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 1, 5, 12, 0, 0), tz)
        )

        # Provide a MONTHLY row in FY 2024; make it "newer" than Q2
        jan = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
            month=1,
        )
        KeyMetricsReport.objects.filter(pk=jan.pk).update(updated_on=timezone.now())

        # Create quarter rows so the incremental branch runs.
        # Only Q2 should be older than the monthly row to trigger refresh.
        now = timezone.now()
        older = now - timezone.timedelta(days=10)
        quarters = {
            1: ((date(2023, 10, 1), date(2023, 12, 31)), now),
            2: ((date(2024, 1, 1), date(2024, 3, 31)), older),
            3: ((date(2024, 4, 1), date(2024, 6, 30)), now),
            4: ((date(2024, 7, 1), date(2024, 9, 30)), now),
        }
        for fq, val in quarters.items():
            (ps, pe), updated = val
            q = KeyMetricsReport.objects.create(
                period_type=KeyMetricsReport.PeriodType.QUARTERLY,
                period_start=ps,
                period_end=pe,
                fiscal_year=2024,
                fiscal_quarter=fq,
            )
            KeyMetricsReport.objects.filter(pk=q.pk).update(updated_on=updated)

        # upsert_quarter is mocked to return None, so when the code reaches the
        # monthly_newer_exists refresh path for Q2 it will take the "is None"
        # branch and continue without incrementing rows_changed.
        changed = build_key_metrics_reports.run(recompute_all=False)

        # No rows changed: month and year upserts return None, and Q2 refresh
        # returned None (so branch continued). Only one refresh attempt expected.
        self.assertEqual(changed, 0)
        self.assertEqual(mock_upsert_quarter.call_count, 1)

    @mock.patch("concordia.tasks.report.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_fiscal_year",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_quarter",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_month",
        return_value=None,
    )
    @mock.patch("concordia.tasks.report.key_metrics.timezone.localdate")
    def test_fiscal_year_recompute_all_none_branch_continue(
        self,
        mock_localdate,
        mock_upsert_month,
        mock_upsert_quarter,
        mock_upsert_year,
        slog,
    ):
        mock_localdate.return_value = date(2024, 5, 20)

        # Ensure monthly scan can initialize.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        tz = timezone.get_current_timezone()
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 5, 10, 12, 0, 0), tz)
        )

        # Ensure at least one fiscal year is present for the FY stage.
        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )

        # Month/quarter upserts are mocked to None; FY upsert also None.
        changed = build_key_metrics_reports.run(recompute_all=True)

        # Nothing should be counted since FY upsert returned None and the code
        # immediately continued the loop without incrementing or logging.
        self.assertEqual(changed, 0)
        self.assertEqual(mock_upsert_year.call_count, 1)

        codes = [kw.get("event_code") for _, kw in slog.info.call_args_list if kw]
        self.assertNotIn("key_metrics_year_upserted", codes)

    @mock.patch("concordia.tasks.report.key_metrics.structured_logger")
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_fiscal_year",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_quarter",
        return_value=None,
    )
    @mock.patch(
        "concordia.tasks.report.key_metrics.KeyMetricsReport.upsert_month",
        return_value=None,
    )
    @mock.patch("concordia.tasks.report.key_metrics.timezone.localdate")
    def test_fiscal_year_incremental_refresh_none_branch_continue(
        self,
        mock_localdate,
        mock_upsert_month,
        mock_upsert_quarter,
        mock_upsert_year,
        slog,
    ):
        mock_localdate.return_value = date(2024, 5, 20)

        # Make monthly stage computable.
        sr = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        tz = timezone.get_current_timezone()
        SiteReport.objects.filter(pk=sr.pk).update(
            created_on=timezone.make_aware(datetime(2024, 5, 10, 12, 0, 0), tz)
        )

        # Existing FY row with older updated_on so a newer quarter will
        # trigger the refresh path.
        fy = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.FISCAL_YEAR,
            period_start=date(2023, 10, 1),
            period_end=date(2024, 9, 30),
            fiscal_year=2024,
        )
        KeyMetricsReport.objects.filter(pk=fy.pk).update(
            updated_on=timezone.make_aware(datetime(2024, 3, 1, 0, 0, 0), tz)
        )

        # Quarter newer than the FY row to make quarter_newer_exists True.
        q2 = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )
        KeyMetricsReport.objects.filter(pk=q2.pk).update(
            updated_on=timezone.make_aware(datetime(2024, 3, 15, 0, 0, 0), tz)
        )

        # FY upsert returns None so the branch is skipped and loop continues.
        changed = build_key_metrics_reports.run(recompute_all=False)

        self.assertEqual(changed, 0)
        self.assertEqual(mock_upsert_year.call_count, 1)

        codes = [kw.get("event_code") for _, kw in slog.info.call_args_list if kw]
        self.assertNotIn("key_metrics_year_refreshed", codes)
        self.assertNotIn("key_metrics_year_created", codes)
        self.assertNotIn("key_metrics_year_upserted", codes)
