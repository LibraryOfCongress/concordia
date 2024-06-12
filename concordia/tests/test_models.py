from datetime import date, timedelta
from secrets import token_hex
from unittest import mock

from django.core.exceptions import ValidationError
from django.db.models.signals import post_save
from django.test import TestCase
from django.utils import timezone

from concordia.models import (
    AssetTranscriptionReservation,
    Campaign,
    CardFamily,
    Resource,
    Transcription,
    TranscriptionStatus,
    UserProfileActivity,
    resource_file_upload_path,
    validated_get_or_create,
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
    create_guide,
    create_resource,
    create_resource_file,
    create_simple_page,
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

    def test_get_ocr_transcript(self):
        self.asset.storage_image = "tests/test-european.jpg"
        self.asset.save()
        phrase = "marrón rápido salta sobre el perro"
        self.assertFalse(phrase in self.asset.get_ocr_transcript())
        self.assertFalse(
            phrase in self.asset.get_ocr_transcript(language="bad-language-code")
        )
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

    def test_get_storage_path(self):
        self.assertEqual(
            self.asset.get_storage_path(filename=self.asset.storage_image),
            "test-campaign/test-project/testitem.0123456789/1.jpg",
        )


class TranscriptionManagerTestCase(CreateTestUsers, TestCase):
    def setUp(self):
        self.transcription1 = create_transcription(
            user=self.create_user(username="tester1"),
            rejected=timezone.now() - timedelta(days=2),
        )
        self.transcription2 = create_transcription(
            asset=self.transcription1.asset, user=get_anonymous_user()
        )

    def test_recent_review_actions(self):
        transcriptions = Transcription.objects
        self.assertEqual(transcriptions.recent_review_actions().count(), 0)

        self.transcription1.accepted = timezone.now()
        self.transcription1.save()
        self.assertEqual(transcriptions.recent_review_actions().count(), 1)

        self.transcription2.rejected = timezone.now()
        self.transcription2.save()
        self.assertEqual(transcriptions.recent_review_actions().count(), 2)

    def test_review_actions(self):
        start = timezone.now() - timedelta(days=5)
        end = timezone.now() - timedelta(days=1)
        self.assertEqual(Transcription.objects.review_actions(start, end).count(), 1)


class TranscriptionTestCase(CreateTestUsers, TestCase):
    def setUp(self):
        self.user = self.create_user("test-user-1")
        self.user2 = self.create_user("test-user-2")
        self.asset = create_asset()
        self.transcription1 = create_transcription(
            user=self.user,
            asset=self.asset,
            rejected=timezone.now() - timedelta(days=2),
        )
        self.transcription2 = create_transcription(asset=self.asset, user=self.user2)

    def test_clean(self):
        bad_transcription = Transcription(asset=self.asset, user=self.user)
        bad_transcription.clean()

        bad_transcription2 = Transcription(
            asset=self.asset,
            user=self.user,
            reviewed_by=self.user,
            accepted=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            bad_transcription2.clean()

        bad_transcription3 = Transcription(
            asset=self.asset,
            user=self.user,
            reviewed_by=self.user2,
            accepted=timezone.now(),
            rejected=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            bad_transcription3.clean()

    def test_status(self):
        transcription = create_transcription(user=self.user, asset=self.asset)
        self.assertEqual(
            transcription.status,
            TranscriptionStatus.CHOICE_MAP[TranscriptionStatus.IN_PROGRESS],
        )

        transcription2 = create_transcription(
            asset=transcription.asset, user=self.user, submitted=timezone.now()
        )
        self.assertEqual(
            transcription2.status,
            TranscriptionStatus.CHOICE_MAP[TranscriptionStatus.SUBMITTED],
        )

        transcription3 = create_transcription(
            asset=transcription.asset,
            user=self.user,
            reviewed_by=self.user2,
            accepted=timezone.now(),
        )
        self.assertEqual(
            transcription3.status,
            TranscriptionStatus.CHOICE_MAP[TranscriptionStatus.COMPLETED],
        )

    def test_reviewing_too_quickly(self):
        transcriptions = Transcription.objects.reviewing_too_quickly()
        self.assertEqual(len(transcriptions), 0)

        self.transcription1.accepted = timezone.now()
        self.transcription1.reviewed_by = self.create_user(username="tester2")
        self.transcription1.save()
        transcription3 = create_transcription(
            asset=self.transcription1.asset,
            user=self.transcription1.user,
            reviewed_by=self.transcription1.reviewed_by,
            accepted=self.transcription1.accepted,
        )
        transcriptions = Transcription.objects.reviewing_too_quickly()
        self.assertEqual(len(transcriptions), 1)
        self.assertIn(transcription3.id, [n[2] for n in transcriptions])

    def test_transcribing_too_quickly(self):
        transcriptions = Transcription.objects.transcribing_too_quickly()
        self.assertEqual(len(transcriptions), 0)

        self.transcription1.submitted = timezone.now()
        self.transcription1.save()
        transcription3 = create_transcription(
            asset=self.transcription1.asset,
            user=self.transcription1.user,
            submitted=self.transcription1.submitted,
        )
        transcriptions = Transcription.objects.transcribing_too_quickly()
        self.assertEqual(len(transcriptions), 1)
        self.assertIn(transcription3.id, [n[2] for n in transcriptions])


class AssetTranscriptionReservationTest(CreateTestUsers, TestCase):
    def setUp(self):
        self.asset = create_asset()
        self.user = self.create_user("test-user")
        self.uid = str(self.user.id).zfill(6)
        self.token = token_hex(22)
        self.reservation_token = self.token + self.uid
        self.reservation = AssetTranscriptionReservation.objects.create(
            asset=self.asset, reservation_token=self.reservation_token
        )

    def test_get_token(self):
        self.assertEqual(self.reservation.get_token(), self.token)

    def test_get_user(self):
        self.assertEqual(self.reservation.get_user(), self.uid)


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

    def test_queryset(self):
        self.assertEqual(Resource.objects.related_links().count(), 1)
        create_resource(
            resource_type=Resource.ResourceType.COMPLETED_TRANSCRIPTION_LINK
        )
        self.assertEqual(Resource.objects.completed_transcription_links().count(), 1)


class ResourceFileTestCase(TestCase):
    def setUp(self):
        self.resource_file = create_resource_file()

    def test_str(self):
        self.assertEqual(self.resource_file.name, str(self.resource_file))

    def test_delete(self):
        with (
            mock.patch.object(self.resource_file.resource, "delete") as delete_mock,
            mock.patch.object(
                self.resource_file.resource, "storage", autospec=True
            ) as storage_mock,
        ):
            storage_mock.exists.return_value = True
            self.resource_file.delete()
            self.assertTrue(delete_mock.called)

        resource_file2 = create_resource_file()
        with (
            mock.patch.object(resource_file2.resource, "delete") as delete_mock,
            mock.patch.object(
                resource_file2.resource, "storage", autospec=True
            ) as storage_mock,
        ):
            storage_mock.exists.return_value = False
            resource_file2.delete()
            self.assertFalse(delete_mock.called)

    def test_resource_file_upload_path(self):
        current_year = date.today().year

        path = resource_file_upload_path(self.resource_file, "SHOULDNTBEUSED.PDF")
        self.assertEqual(path, "file.pdf")

        self.resource_file.path = None

        path = resource_file_upload_path(self.resource_file, "TEST.PDF")
        self.assertEqual(path, f"cm-uploads/resources/{current_year}/test.pdf")

        path = resource_file_upload_path(self.resource_file, "TEST%%s.PDF")
        self.assertEqual(path, f"cm-uploads/resources/{current_year}/test%s.pdf")

        path = resource_file_upload_path(self.resource_file, "%%YTEST.PDF")
        self.assertEqual(path, f"cm-uploads/resources/{current_year}/%ytest.pdf")


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


class GuideTestCase(TestCase):
    def test_str(self):
        guide = create_guide()
        self.assertEqual(guide.title, str(guide))


class SimplePageTestCase(TestCase):
    def test_str(self):
        simple_page = create_simple_page()
        self.assertEqual(f"SimplePage: {simple_page.path}", str(simple_page))


class ValidatedGetOrCreateTestCase(TestCase):
    def test_validated_get_or_create(self):
        kwargs = {
            "title": "Test Campaign",
            "slug": "test-campaign",
        }
        campaign, created = validated_get_or_create(Campaign, **kwargs)
        self.assertTrue(created)
        campaign, created = validated_get_or_create(Campaign, **kwargs)
        self.assertFalse(created)
        self.assertEqual(campaign.title, kwargs["title"])
