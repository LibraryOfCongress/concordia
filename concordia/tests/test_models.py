from unittest.mock import patch

try:
    from unittest.mock import MagicMock
except ImportError:
    from mock import MagicMock

from django.db.models import Sum
from django.db.models.signals import post_save
from django.test import TestCase

from concordia.models import Campaign, Transcription, UserProfileActivity

from .utils import (
    CreateTestUsers,
    create_asset,
    create_banner,
    create_campaign,
    create_transcription,
    create_user_profile_activity,
)


class BannerTestCase(TestCase):
    def setUp(self):
        self.danger_banner = create_banner(alert_status="DANGER")
        self.info_banner = create_banner(alert_status="INFO")
        self.success_banner = create_banner()
        self.warning_banner = create_banner(alert_status="WARNING")

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


class TranscriptionTestCase(CreateTestUsers, TestCase):
    def setUp(self):
        self.user = self.create_test_user("tester")

    def test_on_transcription_save(self):
        asset1 = create_asset()
        asset2 = create_asset(item=asset1.item, slug="slug")
        create_transcription(asset=asset1, user=self.user)
        create_transcription(asset=asset2, user=self.user)
        user_profile_activity = UserProfileActivity.objects.filter(user=self.user)
        aggregate_sums = user_profile_activity.aggregate(Sum("asset_count"))
        self.assertEqual(aggregate_sums["asset_count__sum"], 2)

    @patch("concordia.models.on_transcription_save")
    def test_post_save_signal(self, mock):
        """
        Assert signal is sent with proper arguments
        """
        # Create handler
        handler = MagicMock()
        post_save.connect(handler, sender=Transcription)

        transcription = create_transcription(user=self.user)

        # Assert the signal was called only once with the args
        handler.assert_called_once_with(
            signal=post_save,
            sender=Transcription,
            instance=transcription,
            created=True,
            update_fields=None,
            raw=False,
            using="default",
        )


class UserProfileActivityTestCase(CreateTestUsers, TestCase):
    def setUp(self):
        self.user = self.create_test_user("tester")
        campaign1 = create_campaign(slug="clara-barton-angel-of-the-battlefield")
        self.user_profile_activity = create_user_profile_activity(
            user=self.user,
            campaign=campaign1,
            transcribe_count=29,
            review_count=11,
            asset_count=40,
        )
        self.user_profile_activity.save()
        campaign2 = create_campaign(slug="correspondence-of-theodore-roosevelt")
        user_profile_activity = create_user_profile_activity(
            user=self.user,
            campaign=campaign2,
            transcribe_count=23,
            review_count=11,
            asset_count=34,
        )
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
