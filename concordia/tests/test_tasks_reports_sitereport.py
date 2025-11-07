from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from concordia.models import Campaign, SiteReport, Transcription
from concordia.tasks.reports.sitereport import (
    _daily_active_users,
    campaign_report,
    site_report,
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

    def test_topic_report_zero_assets_emits_warning(self):
        # Create a new topic attached to a project with no items/assets so the
        # topic report computes zero total assets and emits a warning.
        from unittest import mock

        empty_campaign = create_campaign(slug="sr-empty-c")
        empty_project = create_project(campaign=empty_campaign, slug="sr-empty-p")
        empty_topic = create_topic(project=empty_project, slug="sr-empty-t")

        with mock.patch("concordia.tasks.reports.sitereport.structured_logger") as slog:
            site_report()

            warn_calls = [
                c
                for c in slog.warning.call_args_list
                if c.kwargs.get("event_code") == "topic_report_zero_assets"
                and c.kwargs.get("topic") == empty_topic
            ]
            self.assertTrue(warn_calls)
