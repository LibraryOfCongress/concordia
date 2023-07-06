from django.test import TestCase

from concordia.tasks import _daily_active_users


class SiteReportTestCase(TestCase):
    def test_daily_active_users(self):
        self.assertEqual(_daily_active_users(), [])
