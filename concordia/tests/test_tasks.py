from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.cache import cache, caches
from django.test import TestCase, override_settings
from django.utils import timezone
from requests.models import Response

from concordia.models import (
    Campaign,
    NextReviewableCampaignAsset,
    NextReviewableTopicAsset,
    NextTranscribableCampaignAsset,
    NextTranscribableTopicAsset,
    SiteReport,
    Transcription,
    TranscriptionStatus,
)
from concordia.tasks import (
    CacheLockedError,
    _daily_active_users,
    campaign_report,
    clean_next_reviewable_for_campaign,
    clean_next_reviewable_for_topic,
    clean_next_transcribable_for_campaign,
    clean_next_transcribable_for_topic,
    fetch_and_cache_blog_images,
    populate_asset_status_visualization_cache,
    populate_daily_activity_visualization_cache,
    populate_next_reviewable_for_campaign,
    populate_next_reviewable_for_topic,
    populate_next_transcribable_for_campaign,
    populate_next_transcribable_for_topic,
    renew_next_asset_cache,
    site_report,
    unusual_activity,
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

    @mock.patch("concordia.tasks.Transcription.objects")
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
    @mock.patch("concordia.tasks._update_useractivity_cache")
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

    @mock.patch("concordia.tasks.extract_og_image")
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

    @mock.patch("concordia.tasks.update_userprofileactivity_table")
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

    @mock.patch("concordia.tasks.update_userprofileactivity_table")
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

    @mock.patch("concordia.tasks.logger")
    def test_populate_next_transcribable_for_campaign_missing(self, mock_logger):
        populate_next_transcribable_for_campaign(campaign_id=9999)
        mock_logger.error.assert_called_once()

    @mock.patch("concordia.tasks.logger")
    def test_populate_next_transcribable_for_topic_missing(self, mock_logger):
        populate_next_transcribable_for_topic(topic_id=9999)
        mock_logger.error.assert_called_once()

    @mock.patch("concordia.tasks.logger")
    def test_populate_next_reviewable_for_campaign_missing(self, mock_logger):
        populate_next_reviewable_for_campaign(campaign_id=9999)
        mock_logger.error.assert_called_once()

    @mock.patch("concordia.tasks.logger")
    def test_populate_next_reviewable_for_topic_missing(self, mock_logger):
        populate_next_reviewable_for_topic(topic_id=9999)
        mock_logger.error.assert_called_once()

    @mock.patch("concordia.tasks.logger")
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

    @mock.patch("concordia.tasks.logger")
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

    @mock.patch("concordia.tasks.logger")
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

    @mock.patch("concordia.tasks.logger")
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

    @mock.patch("concordia.tasks.logger")
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

    @mock.patch("concordia.tasks.logger")
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

    @mock.patch("concordia.tasks.logger")
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

    @mock.patch("concordia.tasks.logger")
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

    @mock.patch("concordia.tasks.populate_next_transcribable_for_campaign.delay")
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

    @mock.patch("concordia.tasks.populate_next_transcribable_for_topic.delay")
    def test_clean_next_transcribable_for_topic(self, mock_delay):
        self.asset.transcription_status = TranscriptionStatus.COMPLETED
        self.asset.save()
        clean_next_transcribable_for_topic(self.topic.id)
        self.assertFalse(
            NextTranscribableTopicAsset.objects.filter(topic=self.topic).exists()
        )
        mock_delay.assert_called_once_with(self.topic.id)

    @mock.patch("concordia.tasks.populate_next_reviewable_for_campaign.delay")
    def test_clean_next_reviewable_for_campaign(self, mock_delay):
        self.asset.transcription_status = TranscriptionStatus.IN_PROGRESS
        self.asset.save()
        clean_next_reviewable_for_campaign(self.campaign.id)
        self.assertFalse(
            NextReviewableCampaignAsset.objects.filter(campaign=self.campaign).exists()
        )
        mock_delay.assert_called_once_with(self.campaign.id)

    @mock.patch("concordia.tasks.populate_next_reviewable_for_topic.delay")
    def test_clean_next_reviewable_for_topic(self, mock_delay):
        self.asset.transcription_status = TranscriptionStatus.NOT_STARTED
        self.asset.save()
        clean_next_reviewable_for_topic(self.topic.id)
        self.assertFalse(
            NextReviewableTopicAsset.objects.filter(topic=self.topic).exists()
        )
        mock_delay.assert_called_once_with(self.topic.id)

    @mock.patch("concordia.tasks.clean_next_reviewable_for_campaign.delay")
    @mock.patch("concordia.tasks.clean_next_transcribable_for_campaign.delay")
    @mock.patch("concordia.tasks.clean_next_reviewable_for_topic.delay")
    @mock.patch("concordia.tasks.clean_next_transcribable_for_topic.delay")
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

    @mock.patch("concordia.tasks.logger")
    def test_clean_next_transcribable_for_campaign_exception(self, mock_logger):
        with mock.patch.object(
            self.campaign_transcribable, "delete", side_effect=Exception("fail")
        ):
            with mock.patch(
                "concordia.tasks.find_invalid_next_transcribable_campaign_assets",
                return_value=[self.campaign_transcribable],
            ):
                clean_next_transcribable_for_campaign(self.campaign.id)
        mock_logger.exception.assert_called_once()

    @mock.patch("concordia.tasks.logger")
    def test_clean_next_transcribable_for_topic_exception(self, mock_logger):
        with mock.patch.object(
            self.topic_transcribable, "delete", side_effect=Exception("fail")
        ):
            with mock.patch(
                "concordia.tasks.find_invalid_next_transcribable_topic_assets",
                return_value=[self.topic_transcribable],
            ):
                clean_next_transcribable_for_topic(self.topic.id)
        mock_logger.exception.assert_called_once()

    @mock.patch("concordia.tasks.logger")
    def test_clean_next_reviewable_for_campaign_exception(self, mock_logger):
        with mock.patch.object(
            self.campaign_reviewable, "delete", side_effect=Exception("fail")
        ):
            with mock.patch(
                "concordia.tasks.find_invalid_next_reviewable_campaign_assets",
                return_value=[self.campaign_reviewable],
            ):
                clean_next_reviewable_for_campaign(self.campaign.id)
        mock_logger.exception.assert_called_once()

    @mock.patch("concordia.tasks.logger")
    def test_clean_next_reviewable_for_topic_exception(self, mock_logger):
        with mock.patch.object(
            self.topic_reviewable, "delete", side_effect=Exception("fail")
        ):
            with mock.patch(
                "concordia.tasks.find_invalid_next_reviewable_topic_assets",
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

        by_cam = self.cache.get("asset-status-by-campaign")
        self.assertEqual(by_cam["status_labels"], expected_labels)
        self.assertEqual(by_cam["campaign_names"], ["Alpha", "Beta"])
        counts = by_cam["per_campaign_counts"]
        self.assertEqual(counts["not_started"], [1, 0])
        self.assertEqual(counts["in_progress"], [0, 1])
        self.assertEqual(counts["submitted"], [0, 1])
        self.assertEqual(counts["completed"], [0, 1])

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
            transcriptions_saved=5,  # decreased total, which shouldn't happen
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
