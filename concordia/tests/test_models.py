from django.test import TestCase

from concordia.models import Banner, Campaign, UserProfileActivity


class BannerTestCase(TestCase):
    def setUp(self):
        self.danger_banner = Banner(alert_status="DANGER")
        self.info_banner = Banner(alert_status="INFO")
        self.success_banner = Banner(alert_status="SUCCESS")
        self.warning_banner = Banner(alert_status="WARNING")

    def test_alert_class(self):
        self.assertEqual(self.danger_banner.alert_class(), "alert-danger")
        self.assertEqual(self.info_banner.alert_class(), "alert-info")
        self.assertEqual(self.success_banner.alert_class(), "alert-success")
        self.assertEqual(self.warning_banner.alert_class(), "alert-warning")

    def test_btn_class(self):
        self.assertEqual(self.danger_banner.btn_class(), "btn-danger")
        self.assertEqual(self.info_banner.btn_class(), "btn-info")
        self.assertEqual(self.success_banner.btn_class(), "btn-success")
        self.assertEqual(self.warning_banner.btn_class(), "btn-warning")


class UserProfileActivityTestCase(TestCase):
    def setUp(self):
        self.user_profile_activity = UserProfileActivity(
            campaign=Campaign(), transcribe_count=135, review_count=204
        )

    def test_get_status(self):
        self.user_profile_activity.campaign.status = Campaign.Status.ACTIVE
        self.assertEqual(self.user_profile_activity.get_status(), "Active")
        self.user_profile_activity.campaign.status = Campaign.Status.COMPLETED
        self.assertEqual(self.user_profile_activity.get_status(), "Completed")
        self.user_profile_activity.campaign.status = Campaign.Status.RETIRED
        self.assertEqual(self.user_profile_activity.get_status(), "Retired")

    def test_total_actions(self):
        self.assertEqual(self.user_profile_activity.total_actions(), 339)
