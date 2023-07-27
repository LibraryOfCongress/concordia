from django.test import TestCase
from django.utils import timezone

from concordia.models import SiteReport
from concordia.tasks import _daily_active_users, _get_review_actions, site_report
from concordia.utils import get_anonymous_user

from .utils import CreateTestUsers, create_asset, create_transcription


class SiteReportTestCase(CreateTestUsers, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user1 = cls.create_user(username="tester")
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
        site_report()
        cls.site_report = SiteReport.objects.filter(
            report_name=SiteReport.ReportName.TOTAL
        ).first()
        cls.retired_site_report = SiteReport.objects.filter(
            report_name=SiteReport.ReportName.RETIRED_TOTAL
        ).first()
        cls.campaign1_site_report = SiteReport.objects.filter(
            campaign=cls.campaign1
        ).first()

    def test_daily_active_users(self):
        self.assertEqual(_daily_active_users(), 2)

    def test_get_review_actions(self):
        self.assertEqual(_get_review_actions(campaign=self.campaign1), 2)

    def test_campaign_report(self):
        self.assertEqual(self.campaign1_site_report.daily_review_actions, 2)
