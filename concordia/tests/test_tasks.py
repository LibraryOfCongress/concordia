from datetime import datetime

from django.test import TestCase

from concordia.models import SiteReport
from concordia.tasks import _daily_active_users, _get_review_actions, campaign_report
from concordia.utils import get_anonymous_user

from .utils import CreateTestUsers, create_asset, create_transcription


class SiteReportTestCase(CreateTestUsers, TestCase):
    def setUp(self):
        asset = create_asset()
        self.login_user()
        anon = get_anonymous_user()
        create_transcription(asset=asset, user=self.user, accepted=datetime.now())
        create_transcription(
            asset=asset, user=anon, rejected=datetime.now(), reviewed_by=self.user
        )
        self.campaign = asset.item.project.campaign

    def test_daily_active_users(self):
        self.assertEqual(_daily_active_users(), 2)

    def test_campaign_report(self):
        campaign_report(self.campaign)
        self.assertEqual(SiteReport.objects.first().daily_review_actions, 2)

    def test_get_review_actions(self):
        self.assertEqual(_get_review_actions(campaign=self.campaign), 2)
