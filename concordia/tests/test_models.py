from django.contrib.auth.models import User
from django.db.models import Sum
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
        self.user = User()
        self.user.save()
        campaign1 = Campaign.objects.create(
            slug="clara-barton-angel-of-the-battlefield"
        )
        campaign1.save()
        kwargs = {
            "user": self.user,
            "campaign": campaign1,
            "transcribe_count": 29,
            "review_count": 11,
            "asset_count": 40,
        }
        self.user_profile_activity = UserProfileActivity.objects.create(**kwargs)
        self.user_profile_activity.save()
        campaign2 = Campaign.objects.create(slug="correspondence-of-theodore-roosevelt")
        campaign2.save()
        kwargs = {
            "user": self.user,
            "campaign": campaign2,
            "transcribe_count": 23,
            "review_count": 11,
            "asset_count": 34,
        }
        user_profile_activity = UserProfileActivity.objects.create(**kwargs)
        user_profile_activity.save()

    def test_get_status(self):
        self.user_profile_activity.campaign.status = Campaign.Status.ACTIVE
        self.assertEqual(self.user_profile_activity.get_status(), "Active")
        self.user_profile_activity.campaign.status = Campaign.Status.COMPLETED
        self.assertEqual(self.user_profile_activity.get_status(), "Completed")
        self.user_profile_activity.campaign.status = Campaign.Status.RETIRED
        self.assertEqual(self.user_profile_activity.get_status(), "Retired")

    def test_total_actions(self):
        user_profile_activity = UserProfileActivity.objects.filter(user=self.user)
        aggregate_sums = user_profile_activity.aggregate(
            Sum("review_count"), Sum("transcribe_count"), Sum("asset_count")
        )
        self.assertEqual(aggregate_sums["review_count__sum"], 22)
        self.assertEqual(aggregate_sums["transcribe_count__sum"], 52)
        self.assertEqual(aggregate_sums["asset_count__sum"], 74)
