from datetime import timedelta
from unittest import mock

from django.db.models.signals import post_save
from django.test import TestCase
from django.utils import timezone

from concordia.models import (
    Campaign,
    CardFamily,
    Transcription,
    UserProfileActivity,
)
from concordia.utils import get_anonymous_user

from .utils import (
    CreateTestUsers,
    create_asset,
    create_banner,
    create_campaign,
    create_campaign_retirement_progress,
    create_card,
    create_card_family,
    create_carousel_slide,
    create_resource,
    create_resource_file,
    create_tag,
    create_tag_collection,
    create_transcription,
    create_user_profile_activity,
)


class AssetTestCase(CreateTestUsers, TestCase):
    def setUp(self):
        self.asset = create_asset()
        anon = get_anonymous_user()
        create_transcription(asset=self.asset, user=anon)
        create_transcription(
            asset=self.asset,
            user=self.create_test_user(username="tester"),
            reviewed_by=anon,
        )

    def get_ocr_transcript(self):
        self.asset.storage_image = "tests/test-european.jpg"
        self.asset.save()
        phrase = "marrón rápido salta sobre el perro"
        self.assertFalse(phrase in self.asset.get_ocr_transcript())
        self.assertTrue(phrase in self.asset.get_ocr_transcript(language="spa"))

    def test_get_contributor_count(self):
        self.assertEqual(self.asset.get_contributor_count(), 2)

    def test_turn_off_ocr(self):
        self.assertFalse(self.asset.turn_off_ocr())
        self.asset.disable_ocr = True
        self.asset.save()
        self.assertTrue(self.asset.turn_off_ocr())

        self.assertFalse(self.asset.item.turn_off_ocr())
        self.asset.item.disable_ocr = True
        self.asset.item.save()
        self.assertTrue(self.asset.item.turn_off_ocr())

        self.assertFalse(self.asset.item.project.turn_off_ocr())
        self.asset.item.project.disable_ocr = True
        self.asset.item.project.save()
        self.assertTrue(self.asset.item.project.turn_off_ocr())


class TranscriptionManagerTestCase(CreateTestUsers, TestCase):
    def test_recent_review_actions(self):
        transcription1 = create_transcription(
            user=self.create_user(username="tester1"),
            rejected=timezone.now() - timedelta(days=2),
        )
        transcription2 = create_transcription(
            asset=transcription1.asset, user=get_anonymous_user()
        )
        transcriptions = Transcription.objects
        self.assertEqual(transcriptions.recent_review_actions().count(), 0)
        transcription1.accepted = timezone.now()
        transcription1.save()
        self.assertEqual(transcriptions.recent_review_actions().count(), 1)
        transcription2.rejected = timezone.now()
        transcription2.save()
        self.assertEqual(transcriptions.recent_review_actions().count(), 2)


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

    def test_str(self):
        activity = create_user_profile_activity()
        self.assertEqual(f"{activity.user} - {activity.campaign}", str(activity))


class CampaignTestCase(TestCase):
    def test_queryset(self):
        campaign = create_campaign(unlisted=True)
        self.assertIn(campaign, Campaign.objects.unlisted())

        campaign.status = Campaign.Status.COMPLETED
        campaign.save()
        self.assertIn(campaign, Campaign.objects.completed())

        campaign.status = Campaign.Status.RETIRED
        campaign.save()
        self.assertIn(campaign, Campaign.objects.retired())


class CardTestCase(TestCase):
    def test_str(self):
        card = create_card()
        self.assertEqual(card.title, str(card))


class CardFamilyTestCase(TestCase):
    def setUp(self):
        self.family1 = create_card_family(default=True)

    def test_str(self):
        self.assertEqual(self.family1.slug, str(self.family1))

    def test_on_cardfamily_save(self):
        with mock.patch("concordia.models.on_cardfamily_save") as mocked_handler:
            post_save.connect(mocked_handler, sender=CardFamily)
            self.family1.save()
            self.assertTrue(mocked_handler.called)
            self.assertEqual(mocked_handler.call_count, 1)


class ResourceTestCase(TestCase):
    def setUp(self):
        self.resource = create_resource()

    def test_str(self):
        self.assertEqual(self.resource.title, str(self.resource))


class ResourceFileTestCase(TestCase):
    def test_str(self):
        resource_file = create_resource_file()
        self.assertEqual(resource_file.name, str(resource_file))


class TagTestCase(TestCase):
    def test_str(self):
        tag = create_tag()
        self.assertEqual(tag.value, str(tag))


class UserAssetTagCollectionTestCase(TestCase):
    def test_str(self):
        tag_collection = create_tag_collection()
        self.assertEqual(
            "{} - {}".format(tag_collection.asset, tag_collection.user),
            str(tag_collection),
        )


class BannerTestCase(TestCase):
    def setUp(self):
        self.banner = create_banner()

    def test_str(self):
        self.assertEqual(f"Banner: {self.banner.slug}", str(self.banner))

    def test_alert_class(self):
        self.assertEqual(
            self.banner.alert_class(), "alert-" + self.banner.alert_status.lower()
        )

    def test_btn_class(self):
        self.assertEqual(
            self.banner.btn_class(), "btn-" + self.banner.alert_status.lower()
        )


class CarouselSlideTestCase(TestCase):
    def test_str(self):
        slide = create_carousel_slide()
        self.assertEqual(f"CarouselSlide: {slide.headline}", str(slide))


class CampaignRetirementProgressTestCase(TestCase):
    def test_str(self):
        progress = create_campaign_retirement_progress()
        self.assertEqual(f"Removal progress for {progress.campaign}", str(progress))
