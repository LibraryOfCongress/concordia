import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from secrets import token_hex
from unittest import mock

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models import signals
from django.test import TestCase
from django.utils import timezone

from concordia.models import (
    Asset,
    AssetTranscriptionReservation,
    Campaign,
    CardFamily,
    ConcordiaUser,
    KeyMetricsReport,
    MediaType,
    NextReviewableCampaignAsset,
    NextReviewableTopicAsset,
    NextTranscribableCampaignAsset,
    NextTranscribableTopicAsset,
    Resource,
    SiteReport,
    Topic,
    Transcription,
    TranscriptionStatus,
    UserProfile,
    UserProfileActivity,
    _update_useractivity_cache,
    resource_file_upload_path,
    update_userprofileactivity_table,
    validated_get_or_create,
)
from concordia.signals.handlers import create_user_profile, on_transcription_save
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
    create_item,
    create_resource,
    create_resource_file,
    create_simple_page,
    create_tag,
    create_tag_collection,
    create_topic,
    create_transcription,
    create_user_profile_activity,
)


class AssetTestCase(CreateTestUsers, TestCase):
    def setUp(self):
        self.asset = create_asset()
        self.anon = get_anonymous_user()
        create_transcription(asset=self.asset, user=self.anon)
        create_transcription(
            asset=self.asset,
            user=self.create_test_user(username="tester"),
            reviewed_by=self.anon,
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
            self.asset.get_storage_path(filename=self.asset.storage_image.name),
            "test-campaign/test-project/testitem.0123456789/1.jpg",
        )

    def test_saving_without_campaign(self):
        try:
            Asset.objects.create(
                item=self.asset.item,
                title="No campaign",
                slug="no-campaign",
                media_type=MediaType.IMAGE,
                storage_image="unittest1.jpg",
            )
        except (ValidationError, ObjectDoesNotExist):
            self.fail("Creating an Asset without a campaign failed validation.")

    def test_rollforward_with_only_rollforward_transcriptions(self):
        asset = create_asset(slug="rollforward-test", item=self.asset.item)
        create_transcription(asset=asset, user=self.anon, rolled_forward=True)
        with self.assertRaisesMessage(
            ValueError,
            "Can not rollforward transcription on an asset with "
            "no non-rollforward transcriptions",
        ):
            asset.rollforward_transcription(self.anon)

    def test_rollforward_with_too_many_rollforward_transcriptions(self):
        asset = create_asset(slug="rollforward-test", item=self.asset.item)
        transcription1 = create_transcription(asset=asset, user=self.anon)
        create_transcription(
            asset=asset, user=self.anon, supersedes=transcription1, rolled_forward=True
        )
        create_transcription(
            asset=asset, user=self.anon, supersedes=transcription1, rolled_forward=True
        )
        with self.assertRaisesMessage(
            ValueError,
            "More rollforward transcription exist than non-roll-forward "
            "transcriptions, which shouldn't be possible. Possibly "
            "incorrectly modified transcriptions for this asset.",
        ):
            asset.rollforward_transcription(self.anon)

    def test_rollforward_with_no_superseded_transcription(self):
        # This isn't a state that would happen normally, but could be created
        # accidentally when manually editing transcription history
        asset = create_asset(slug="rollforward-test", item=self.asset.item)
        transcription1 = create_transcription(asset=asset, user=self.anon)
        create_transcription(asset=asset, user=self.anon, supersedes=transcription1)
        create_transcription(
            asset=asset, user=self.anon, rolled_back=True, source=transcription1
        )
        with self.assertRaisesMessage(
            ValueError,
            "Can not rollforward transcription on an asset if the latest "
            "rollback transcription did not supersede a previous transcription",
        ):
            asset.rollforward_transcription(self.anon)

    def test_get_storage_path_handles_jpeg(self):
        # Ensure ".jpeg" is normalized to ".jpg"
        expected = self.asset.get_asset_image_filename("jpg")
        self.assertEqual(self.asset.get_storage_path("anything.jpeg"), expected)


class ItemModelTests(TestCase):
    def test_thumbnail_link_prefers_image_url_when_present(self):
        item = create_item()

        class Img:
            url = "http://example.test/media/thumb.jpg"

        item.thumbnail_image = Img()
        self.assertEqual(item.thumbnail_link, Img.url)

    def test_thumbnail_link_falls_back_when_image_url_raises(self):
        # If .url access raises ValueError, fall back to thumbnail_url
        item = create_item()

        class BadImg:
            @property
            def url(self):
                raise ValueError("missing from storage")

        item.thumbnail_image = BadImg()
        item.thumbnail_url = "http://example.test/media/fallback.jpg"
        self.assertEqual(item.thumbnail_link, item.thumbnail_url)

    def test_thumbnail_link_returns_thumbnail_url_when_no_image(self):
        item = create_item()
        item.thumbnail_image = None
        item.thumbnail_url = "http://example.test/media/fallback.jpg"
        self.assertEqual(item.thumbnail_link, item.thumbnail_url)

    def test_thumbnail_link_returns_none_when_no_image_or_url(self):
        item = create_item()
        item.thumbnail_image = None
        item.thumbnail_url = None
        self.assertIsNone(item.thumbnail_link)


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

    def test_review_incidents(self):
        self.transcription1.accepted = timezone.now()
        self.transcription1.reviewed_by = self.create_user(username="tester2")
        self.transcription1.save()
        self.transcription2.accepted = self.transcription1.accepted + timedelta(
            seconds=29
        )
        self.transcription2.reviewed_by = self.transcription1.reviewed_by
        self.transcription2.save()
        create_transcription(
            asset=self.transcription1.asset,
            user=self.transcription1.user,
            reviewed_by=self.transcription1.reviewed_by,
            rejected=self.transcription2.accepted + timedelta(seconds=29),
        )
        create_transcription(
            asset=self.transcription1.asset,
            user=self.transcription1.user,
            reviewed_by=self.transcription1.reviewed_by,
            rejected=self.transcription2.accepted + timedelta(seconds=58),
        )
        users = Transcription.objects.review_incidents()
        self.assertNotIn(self.transcription1.user.id, users)

        transcription3 = create_transcription(
            asset=self.transcription1.asset,
            user=self.transcription1.user,
            reviewed_by=self.transcription1.reviewed_by,
            accepted=self.transcription1.accepted + timedelta(seconds=58),
        )
        transcription4 = create_transcription(
            asset=self.transcription1.asset,
            user=self.transcription1.user,
            reviewed_by=self.transcription1.reviewed_by,
            accepted=transcription3.accepted + timedelta(minutes=1, seconds=1),
        )
        users = Transcription.objects.review_incidents()
        self.assertEqual(len(users), 1)
        self.assertEqual(
            users[0],
            (
                self.transcription1.reviewed_by.id,
                self.transcription1.reviewed_by.username,
                2,
                4,
            ),
        )

        create_transcription(
            asset=self.transcription1.asset,
            user=self.transcription1.user,
            reviewed_by=self.transcription1.reviewed_by,
            accepted=transcription4.accepted + timedelta(seconds=29),
        )
        create_transcription(
            asset=self.transcription1.asset,
            user=self.transcription1.user,
            reviewed_by=self.transcription1.reviewed_by,
            accepted=transcription4.accepted + timedelta(seconds=58),
        )
        users = Transcription.objects.review_incidents()
        self.assertEqual(len(users), 1)
        self.assertEqual(
            users[0],
            (
                self.transcription1.reviewed_by.id,
                self.transcription1.reviewed_by.username,
                4,
                6,
            ),
        )

    def test_transcribe_incidents(self):
        self.transcription1.submitted = timezone.now()
        self.transcription1.save()
        self.transcription2.submitted = self.transcription1.submitted + timedelta(
            seconds=29
        )
        self.transcription2.user = self.transcription1.user
        self.transcription2.save()
        users = Transcription.objects.transcribe_incidents()
        self.assertEqual(len(users), 0)
        self.assertNotIn(self.transcription1.user.id, users)

        transcription3 = create_transcription(
            asset=create_asset(slug="asset-two", item=self.transcription1.asset.item),
            user=self.transcription1.user,
            submitted=self.transcription1.submitted + timedelta(seconds=58),
        )
        transcription4 = create_transcription(
            asset=create_asset(slug="asset-three", item=self.transcription1.asset.item),
            user=self.transcription1.user,
            submitted=transcription3.submitted + timedelta(minutes=1, seconds=1),
        )
        create_transcription(
            asset=transcription4.asset,
            user=self.transcription1.user,
            submitted=transcription4.submitted + timedelta(seconds=59),
        )
        users = Transcription.objects.transcribe_incidents()
        self.assertEqual(len(users), 1)
        self.assertEqual(
            users[0],
            (self.transcription1.user.id, self.transcription1.user.username, 2, 5),
        )

        create_transcription(
            asset=create_asset(slug="asset-five", item=self.transcription1.asset.item),
            user=self.transcription1.user,
            submitted=self.transcription1.submitted + timedelta(minutes=1, seconds=59),
        )
        users = Transcription.objects.transcribe_incidents()
        self.assertEqual(len(users), 1)
        self.assertEqual(
            users[0],
            (self.transcription1.user.id, self.transcription1.user.username, 3, 6),
        )

    def test_review_incidents_returns_empty_when_counts_zero(self):
        reviewer = self.create_user(username="rev-zero")
        asset = self.transcription1.asset

        t1 = create_transcription(
            asset=asset,
            user=self.create_user(username="u-a"),
            reviewed_by=reviewer,
            accepted=timezone.now() - timedelta(minutes=5),
        )
        create_transcription(
            asset=asset,
            user=self.create_user(username="u-b"),
            reviewed_by=reviewer,
            accepted=t1.accepted + timedelta(seconds=61),
        )

        out = Transcription.objects.review_incidents()
        self.assertEqual(out, [])

    def test_user_review_incidents_no_threshold_hit(self):
        asset = self.transcription1.asset

        reviewer = self.create_user("reviewer-1")
        reviewer_proxy = ConcordiaUser.objects.get(pk=reviewer.pk)

        base = timezone.now()
        create_transcription(
            asset=asset,
            user=self.create_user("ri_u1"),
            reviewed_by=reviewer_proxy,
            accepted=base,
        )
        create_transcription(
            asset=asset,
            user=self.create_user("ri_u2"),
            reviewed_by=reviewer_proxy,
            accepted=base + timedelta(seconds=61),
        )

        recent = Transcription.objects.filter(accepted__isnull=False)
        incidents = reviewer_proxy.review_incidents(recent)
        self.assertEqual(incidents, 0)

    def test_review_incidents_no_threshold_match_inner_loop_break(self):
        # Two accepts for same reviewer but >60s apart:
        a1 = create_asset(slug="rev-gap-a1", item=self.transcription1.asset.item)
        a2 = create_asset(slug="rev-gap-a2", item=a1.item)
        reviewer = self.create_user("reviewer-1")

        t0 = timezone.now()
        create_transcription(
            asset=a1, user=self.create_user("u1"), reviewed_by=reviewer, accepted=t0
        )
        create_transcription(
            asset=a2,
            user=self.create_user("u2"),
            reviewed_by=reviewer,
            accepted=t0 + timedelta(seconds=61),
        )

        recent = Transcription.objects.filter(accepted__isnull=False)
        reviewer_proxy = ConcordiaUser.objects.get(pk=reviewer.pk)

        incidents = reviewer_proxy.review_incidents(recent)
        self.assertEqual(incidents, 0)

    def test_review_incidents_loops_until_threshold(self):
        reviewer = self.create_user(username="test-reviewer-1")

        # Three accepts within 60s so threshold=3 will require two inner
        # iterations (count goes 1->2, not equal to threshold, then 2->3)
        base = timezone.now()
        create_transcription(
            asset=self.transcription1.asset,
            user=self.transcription1.user,
            reviewed_by=reviewer,
            accepted=base,
        )
        create_transcription(
            asset=self.transcription1.asset,
            user=self.transcription1.user,
            reviewed_by=reviewer,
            accepted=base + timedelta(seconds=20),
        )
        create_transcription(
            asset=self.transcription1.asset,
            user=self.transcription1.user,
            reviewed_by=reviewer,
            accepted=base + timedelta(seconds=40),
        )

        recent_accepts = Transcription.objects.filter(
            accepted__gte=base - timedelta(seconds=1)
        )

        reviewer_proxy = ConcordiaUser.objects.get(id=reviewer.id)

        incidents = reviewer_proxy.review_incidents(
            recent_accepts=recent_accepts, threshold=3
        )
        self.assertEqual(incidents, 1)


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

    def test_campaign_slug(self):
        self.assertEqual(
            self.asset.item.project.campaign.slug, self.transcription1.campaign_slug()
        )

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

    @mock.patch("concordia.tests.test_models.on_transcription_save")
    def test_save(self, mock_handler):
        signals.post_save.connect(on_transcription_save, sender=Transcription)

        transcription = create_transcription(asset=self.asset)
        self.assertTrue(mock_handler.called)
        self.assertEqual(mock_handler.call_count, 1)

        transcription.save()
        self.assertEqual(mock_handler.call_count, 2)

        signals.post_save.disconnect(on_transcription_save, sender=Transcription)

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


class SignalHandlersTest(CreateTestUsers, TestCase):
    @mock.patch("django.core.cache.cache.get")
    @mock.patch("django.core.cache.cache.set")
    def test_update_useractivity_cache(self, mock_set, mock_get):
        campaign = create_campaign()
        user = self.create_test_user()
        mock_get.return_value = {}
        _update_useractivity_cache(user.id, campaign.id, "transcribe")
        self.assertEqual(mock_set.call_count, 1)
        expected_key = f"userprofileactivity_{campaign.pk}"
        expected_value = {user.id: (1, 0)}
        mock_set.assert_called_with(expected_key, expected_value, timeout=None)

        reviewed_by = self.create_test_user(username="testuser2")
        mock_get.return_value = {}
        _update_useractivity_cache(reviewed_by.id, campaign.id, "review")
        self.assertEqual(mock_set.call_count, 2)
        expected_value = {reviewed_by.id: (0, 1)}
        mock_set.assert_called_with(expected_key, expected_value, timeout=None)


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


class UserProfileTestCase(CreateTestUsers, TestCase):
    def test_update_userprofileactivity_table(self):
        signals.post_save.disconnect(
            create_user_profile, sender=settings.AUTH_USER_MODEL
        )

        user = self.create_test_user()
        self.assertFalse(hasattr(user, "profile"))

        transcription = create_transcription(user=user)
        update_userprofileactivity_table(
            user, transcription.asset.item.project.campaign.id, "transcribe_count"
        )

        self.assertTrue(hasattr(user, "profile"))
        self.assertEqual(user.profile.transcribe_count, 1)

        signals.post_save.connect(create_user_profile, sender=settings.AUTH_USER_MODEL)

    def test_update_userprofileactivity_table_updates_existing_and_profile(self):
        # Avoid auto-profile creation so we control both branches
        signals.post_save.disconnect(
            create_user_profile, sender=settings.AUTH_USER_MODEL
        )

        user = self.create_test_user()
        UserProfile.objects.create(user=user)

        transcription = create_transcription(user=user)
        campaign = transcription.asset.item.project.campaign
        upa, _ = UserProfileActivity.objects.get_or_create(
            user=user, campaign=campaign, defaults={"transcribe_count": 1}
        )

        update_userprofileactivity_table(user, campaign.id, "transcribe_count")

        # F() increments apply on save; refresh to observe DB values
        upa.refresh_from_db()
        user.refresh_from_db()
        user.profile.refresh_from_db()

        self.assertEqual(upa.transcribe_count, 2)
        self.assertEqual(user.profile.transcribe_count, 1)

        signals.post_save.connect(create_user_profile, sender=settings.AUTH_USER_MODEL)


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
            signals.post_save.connect(mocked_handler, sender=CardFamily)
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


class NextAssetModelTests(TestCase):
    def setUp(self):
        self.asset = create_asset()
        self.topic = create_topic(project=self.asset.item.project)
        self.campaign = self.asset.campaign
        self.project = self.asset.item.project

    def test_create_next_transcribable_campaign_asset(self):
        obj = NextTranscribableCampaignAsset.objects.create(
            asset=self.asset,
            item=self.asset.item,
            item_item_id=self.asset.item.item_id,
            project=self.project,
            project_slug=self.project.slug,
            sequence=self.asset.sequence,
            campaign=self.campaign,
        )
        self.assertEqual(str(obj), self.asset.title)
        self.assertEqual(obj.transcription_status, "not_started")

    def test_create_next_reviewable_campaign_asset(self):
        obj = NextReviewableCampaignAsset.objects.create(
            asset=self.asset,
            item=self.asset.item,
            item_item_id=self.asset.item.item_id,
            project=self.project,
            project_slug=self.project.slug,
            sequence=self.asset.sequence,
            campaign=self.campaign,
        )
        self.assertEqual(str(obj), self.asset.title)
        self.assertEqual(obj.transcriber_ids, [])

    def test_create_next_transcribable_topic_asset(self):
        obj = NextTranscribableTopicAsset.objects.create(
            asset=self.asset,
            item=self.asset.item,
            item_item_id=self.asset.item.item_id,
            project=self.project,
            project_slug=self.project.slug,
            sequence=self.asset.sequence,
            topic=self.topic,
        )
        self.assertEqual(obj.transcription_status, "not_started")

    def test_create_next_reviewable_topic_asset(self):
        obj = NextReviewableTopicAsset.objects.create(
            asset=self.asset,
            item=self.asset.item,
            item_item_id=self.asset.item.item_id,
            project=self.project,
            project_slug=self.project.slug,
            sequence=self.asset.sequence,
            topic=self.topic,
        )
        self.assertEqual(obj.transcriber_ids, [])

    def test_needed_for_campaign_respects_target_count(self):
        manager = NextTranscribableCampaignAsset.objects
        current_needed = manager.needed_for_campaign(self.campaign.id)
        self.assertEqual(current_needed, settings.NEXT_TRANSCRIBABE_ASSET_COUNT)

        # Add one and check count again
        manager.create(
            asset=self.asset,
            item=self.asset.item,
            item_item_id=self.asset.item.item_id,
            project=self.project,
            project_slug=self.project.slug,
            sequence=self.asset.sequence,
            campaign=self.campaign,
        )
        new_needed = manager.needed_for_campaign(self.campaign.id)
        self.assertEqual(new_needed, settings.NEXT_TRANSCRIBABE_ASSET_COUNT - 1)

    def test_needed_for_topic_respects_target_count(self):
        manager = NextReviewableTopicAsset.objects
        current_needed = manager.needed_for_topic(self.topic.id)
        self.assertEqual(current_needed, settings.NEXT_REVIEWABLE_ASSET_COUNT)

        manager.create(
            asset=self.asset,
            item=self.asset.item,
            item_item_id=self.asset.item.item_id,
            project=self.project,
            project_slug=self.project.slug,
            sequence=self.asset.sequence,
            topic=self.topic,
        )
        new_needed = manager.needed_for_topic(self.topic.id)
        self.assertEqual(new_needed, settings.NEXT_REVIEWABLE_ASSET_COUNT - 1)

    def test_needed_for_campaign_raises_without_target(self):
        from django.db import models

        from concordia.models import NextCampaignAssetManager

        class DummyManager(NextCampaignAssetManager):
            target_count = None

        class DummyModel(models.Model):
            campaign = models.ForeignKey("concordia.Campaign", on_delete=models.CASCADE)
            objects = DummyManager()

            class Meta:
                app_label = "concordia"

        with self.assertRaises(NotImplementedError):
            DummyModel.objects.needed_for_campaign(self.campaign.id)

    def test_needed_for_topic_raises_without_target(self):
        from django.db import models

        from concordia.models import NextTopicAssetManager

        class DummyManager(NextTopicAssetManager):
            target_count = None

        class DummyModel(models.Model):
            topic = models.ForeignKey("concordia.Topic", on_delete=models.CASCADE)
            objects = DummyManager()

            class Meta:
                app_label = "concordia"

        with self.assertRaises(NotImplementedError):
            DummyModel.objects.needed_for_topic(self.topic.id)

    def test_needed_for_campaign_with_explicit_target_count(self):
        manager = NextTranscribableCampaignAsset.objects
        # Should return full count when no assets exist yet
        needed = manager.needed_for_campaign(self.campaign.id, target_count=10)
        self.assertEqual(needed, 10)

        # Add one asset
        manager.create(
            asset=self.asset,
            item=self.asset.item,
            item_item_id=self.asset.item.item_id,
            project=self.project,
            project_slug=self.project.slug,
            sequence=self.asset.sequence,
            campaign=self.campaign,
        )

        needed = manager.needed_for_campaign(self.campaign.id, target_count=10)
        self.assertEqual(needed, 9)

    def test_needed_for_topic_with_explicit_target_count(self):
        manager = NextReviewableTopicAsset.objects
        needed = manager.needed_for_topic(self.topic.id, target_count=5)
        self.assertEqual(needed, 5)

        manager.create(
            asset=self.asset,
            item=self.asset.item,
            item_item_id=self.asset.item.item_id,
            project=self.project,
            project_slug=self.project.slug,
            sequence=self.asset.sequence,
            topic=self.topic,
        )

        needed = manager.needed_for_topic(self.topic.id, target_count=5)
        self.assertEqual(needed, 4)


class SiteReportAndManagerTestCase(TestCase):
    def _aware(self, y, m, d, hh=12, mm=0, ss=0):
        tz = timezone.get_current_timezone()
        return timezone.make_aware(datetime(y, m, d, hh, mm, ss), tz)

    def _mk_sr(
        self,
        *,
        dt,
        report_name=None,
        campaign=None,
        topic=None,
        **kwargs,
    ):
        sr = SiteReport.objects.create(
            report_name=report_name or "",
            campaign=campaign,
            topic=topic,
            **kwargs,
        )
        # Set created_on deterministically for ordering logic
        SiteReport.objects.filter(pk=sr.pk).update(created_on=dt)
        return SiteReport.objects.get(pk=sr.pk)

    def test_calculate_assets_started(self):
        # Uses (assets_total - assets_not_started) deltas; floor at 0.
        v = SiteReport.calculate_assets_started(
            previous_assets_total=100,
            previous_assets_not_started=100,
            current_assets_total=107,
            current_assets_not_started=92,
        )
        self.assertEqual(v, 15)

        # None treated as 0.
        v2 = SiteReport.calculate_assets_started(
            previous_assets_total=None,
            previous_assets_not_started=None,
            current_assets_total=200,
            current_assets_not_started=190,
        )
        self.assertEqual(v2, 10)

        # Negative deltas are floored at 0.
        v3 = SiteReport.calculate_assets_started(
            previous_assets_total=107,
            previous_assets_not_started=92,
            current_assets_total=100,
            current_assets_not_started=90,
        )
        self.assertEqual(v3, 0)

    def test_series_navigation_and_sums(self):
        # Site-wide TOTAL series snapshots across three days
        d1 = self._aware(2024, 1, 10)
        d2 = self._aware(2024, 1, 20)
        d3 = self._aware(2024, 1, 31)

        r1 = self._mk_sr(
            dt=d1,
            report_name=SiteReport.ReportName.TOTAL,
            assets_started=3,
        )
        r2 = self._mk_sr(
            dt=d2,
            report_name=SiteReport.ReportName.TOTAL,
            assets_started=7,
        )
        r3 = self._mk_sr(
            dt=d3,
            report_name=SiteReport.ReportName.TOTAL,
            assets_started=10,
        )

        prev = SiteReport.objects.previous_in_series(
            report_name=SiteReport.ReportName.TOTAL,
            before=self._aware(2024, 1, 25),
        )
        self.assertEqual(prev.pk, r2.pk)

        # last_on_or_before_date_for_series
        last = SiteReport.objects.last_on_or_before_date_for_series(
            report_name=SiteReport.ReportName.TOTAL,
            on_or_before_date=date(2024, 1, 31),
        )
        self.assertEqual(last.pk, r3.pk)

        first = SiteReport.objects.first_on_or_after_date_for_series(
            report_name=SiteReport.ReportName.TOTAL,
            on_or_after_date=date(2024, 1, 15),
            on_or_before_date=date(2024, 1, 29),
        )
        self.assertEqual(first.pk, r2.pk)

        self.assertEqual(r2.previous_in_series().pk, r1.pk)
        self.assertEqual(r2.next_in_series().pk, r3.pk)

        summed = SiteReport.objects.sum_assets_started_for_series_between_dates(
            report_name=SiteReport.ReportName.TOTAL,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )
        self.assertEqual(summed, 3 + 7 + 10)

    def test_per_campaign_and_topic_series_filters(self):
        camp = Campaign.objects.create(title="C1", slug="c1")
        # Per-campaign series
        d1 = self._aware(2023, 12, 1)
        d2 = self._aware(2023, 12, 2)
        s1 = self._mk_sr(dt=d1, campaign=camp, assets_total=1)
        s2 = self._mk_sr(dt=d2, campaign=camp, assets_total=2)

        prev = SiteReport.objects.previous_for_instance(s2)
        nxt = SiteReport.objects.next_for_instance(s1)
        self.assertEqual(prev.pk, s1.pk)
        self.assertEqual(nxt.pk, s2.pk)

        # Unspecified series (fallback), ensure no crash and no result
        none_prev = SiteReport.objects.previous_in_series()
        self.assertIsNone(none_prev)

    def test__series_filter_campaign_branch(self):
        camp = Campaign.objects.create(title="C", slug="c")
        # Two rows in same per-campaign series
        s1 = SiteReport.objects.create(campaign=camp, assets_total=1)
        s2 = SiteReport.objects.create(campaign=camp, assets_total=2)

        # Force a deterministic order
        SiteReport.objects.filter(pk=s1.pk).update(created_on=self._aware(2024, 1, 1))
        SiteReport.objects.filter(pk=s2.pk).update(created_on=self._aware(2024, 1, 2))

        prev = SiteReport.objects.previous_in_series(
            campaign=camp, before=self._aware(2024, 1, 3)
        )
        self.assertEqual(prev.pk, s2.pk)

        # And last_on_or_before path also using campaign filter
        last = SiteReport.objects.last_on_or_before_date_for_series(
            campaign=camp, on_or_before_date=date(2024, 1, 2)
        )
        self.assertEqual(last.pk, s2.pk)

    def test__series_filter_topic_branch(self):
        topic = Topic.objects.create(title="T", slug="t")
        s1 = SiteReport.objects.create(topic=topic, assets_total=1)
        s2 = SiteReport.objects.create(topic=topic, assets_total=2)
        SiteReport.objects.filter(pk=s1.pk).update(created_on=self._aware(2024, 2, 1))
        SiteReport.objects.filter(pk=s2.pk).update(created_on=self._aware(2024, 2, 2))

        first = SiteReport.objects.first_on_or_after_date_for_series(
            topic=topic,
            on_or_after_date=date(2024, 2, 1),
            on_or_before_date=date(2024, 2, 5),
        )
        self.assertEqual(first.pk, s1.pk)

    def test_series_filter_for_instance_topic_branch(self):
        topic = Topic.objects.create(title="T2", slug="t2")
        a = SiteReport.objects.create(topic=topic, assets_total=10)
        b = SiteReport.objects.create(topic=topic, assets_total=20)

        SiteReport.objects.filter(pk=a.pk).update(created_on=self._aware(2024, 3, 1))
        SiteReport.objects.filter(pk=b.pk).update(created_on=self._aware(2024, 3, 2))

        # IMPORTANT: refresh to pick up the updated created_on values
        a.refresh_from_db()
        b.refresh_from_db()

        self.assertEqual(b.previous_in_series().pk, a.pk)
        self.assertEqual(a.next_in_series().pk, b.pk)

    def test_series_filter_for_instance_retired_and_fallback(self):
        r = SiteReport.objects.create(
            report_name=SiteReport.ReportName.RETIRED_TOTAL, assets_total=1
        )
        # With only a single row, previous/next resolve via the RETIRED series Q()
        self.assertIsNone(r.previous_in_series())
        self.assertIsNone(r.next_in_series())

        blank = SiteReport.objects.create(assets_total=3)  # report_name=""
        self.assertIsNone(blank.previous_in_series())
        self.assertIsNone(blank.next_in_series())

    def test_to_debug_dict_includes_related_fields_and_counters(self):
        camp = Campaign.objects.create(title="CTitle", slug="cslug")
        topic = Topic.objects.create(title="TTitle", slug="tslug")

        sr_campaign = SiteReport.objects.create(
            campaign=camp, assets_total=9, assets_published=3
        )
        sr_topic = SiteReport.objects.create(
            topic=topic, items_published=4, items_unpublished=1
        )

        d1 = sr_campaign.to_debug_dict()
        self.assertIn("campaign", d1)
        self.assertEqual(d1["campaign"]["id"], camp.id)
        self.assertEqual(d1["campaign"]["title"], "CTitle")
        self.assertEqual(d1["campaign"]["slug"], "cslug")
        self.assertIn("counters", d1)
        self.assertEqual(d1["counters"]["assets_total"], 9)
        self.assertEqual(d1["counters"]["assets_published"], 3)

        d2 = sr_topic.to_debug_dict()
        self.assertIn("topic", d2)
        self.assertEqual(d2["topic"]["id"], topic.id)
        self.assertEqual(d2["topic"]["title"], "TTitle")
        self.assertEqual(d2["topic"]["slug"], "tslug")
        self.assertEqual(d2["counters"]["items_published"], 4)
        self.assertEqual(d2["counters"]["items_unpublished"], 1)

    def test_first_on_or_after_with_upper_bound_campaign(self):
        camp = Campaign.objects.create(title="C-Bound", slug="c-bound")
        a = SiteReport.objects.create(campaign=camp)
        b = SiteReport.objects.create(campaign=camp)
        SiteReport.objects.filter(pk=a.pk).update(created_on=self._aware(2024, 5, 1))
        SiteReport.objects.filter(pk=b.pk).update(created_on=self._aware(2024, 5, 2))

        out = SiteReport.objects.first_on_or_after_date_for_series(
            campaign=camp,
            on_or_after_date=date(2024, 5, 1),
            on_or_before_date=date(2024, 5, 1),
        )
        self.assertEqual(out.pk, a.pk)

    def test_previous_in_series_defaults_to_now(self):
        r1 = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        r2 = SiteReport.objects.create(report_name=SiteReport.ReportName.TOTAL)
        SiteReport.objects.filter(pk=r1.pk).update(created_on=self._aware(2024, 1, 10))
        SiteReport.objects.filter(pk=r2.pk).update(created_on=self._aware(2024, 1, 20))
        out = SiteReport.objects.previous_in_series(
            report_name=SiteReport.ReportName.TOTAL
        )
        self.assertEqual(out.pk, r2.pk)

    def test_sum_assets_started_treats_null_as_zero(self):
        r1 = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL, assets_started=None
        )
        r2 = SiteReport.objects.create(
            report_name=SiteReport.ReportName.TOTAL, assets_started=None
        )
        SiteReport.objects.filter(pk=r1.pk).update(created_on=self._aware(2024, 2, 1))
        SiteReport.objects.filter(pk=r2.pk).update(created_on=self._aware(2024, 2, 2))
        total = SiteReport.objects.sum_assets_started_for_series_between_dates(
            report_name=SiteReport.ReportName.TOTAL,
            start_date=date(2024, 2, 1),
            end_date=date(2024, 2, 28),
        )
        self.assertEqual(total, 0)

    def test_to_debug_dict_campaign_status_and_topic_loop(self):
        camp = Campaign.objects.create(
            title="Camp", slug="camp"
        )  # status has a default
        topic = Topic.objects.create(title="Top", slug="top")

        sr_campaign = SiteReport.objects.create(campaign=camp, assets_total=1)
        sr_topic = SiteReport.objects.create(topic=topic, assets_total=2)

        d1 = sr_campaign.to_debug_dict()
        self.assertIn("campaign", d1)
        # ensure the loop includes all three fields, including status
        self.assertEqual(d1["campaign"]["title"], "Camp")
        self.assertEqual(d1["campaign"]["slug"], "camp")
        self.assertIn("status", d1["campaign"])

        d2 = sr_topic.to_debug_dict()
        self.assertIn("topic", d2)
        # ensure the loop includes both fields for topic
        self.assertEqual(d2["topic"]["title"], "Top")
        self.assertEqual(d2["topic"]["slug"], "top")

    def test_to_debug_json_serializes_and_includes_counters(self):
        camp = Campaign.objects.create(title="CJ", slug="cj")
        sr = SiteReport.objects.create(
            campaign=camp, assets_total=4, assets_published=2
        )
        out = sr.to_debug_json()
        parsed = json.loads(out)

        # basic shape checks
        self.assertIn("created_on", parsed)  # ISO string
        self.assertEqual(parsed["report_name"], "")
        self.assertEqual(parsed["campaign"]["id"], camp.id)

        # counters included and numeric values preserved
        self.assertEqual(parsed["counters"]["assets_total"], 4)
        self.assertEqual(parsed["counters"]["assets_published"], 2)

    def test_first_on_or_after_without_upper_bound_topic(self):
        # Create two topic reports; query without an upper bound s
        # hould still return the earliest on/after.
        topic = Topic.objects.create(title="UBT", slug="ubt")
        s1 = SiteReport.objects.create(topic=topic)
        s2 = SiteReport.objects.create(topic=topic)
        SiteReport.objects.filter(pk=s1.pk).update(created_on=self._aware(2024, 6, 1))
        SiteReport.objects.filter(pk=s2.pk).update(created_on=self._aware(2024, 6, 2))

        out = SiteReport.objects.first_on_or_after_date_for_series(
            topic=topic,
            on_or_after_date=date(2024, 6, 2),
            # no on_or_before_date here on purpose
        )
        self.assertEqual(out.pk, s2.pk)

    def test_to_debug_dict_skips_none_campaign_attrs(self):
        # Force the related-object cache to a stub that lacks some attrs
        from types import SimpleNamespace

        camp = Campaign.objects.create(title="C", slug="c")
        sr = SiteReport.objects.create(campaign=camp, assets_total=1)

        # Populate fields_cache so descriptor returns this stub instead of hitting DB
        sr._state.fields_cache["campaign"] = SimpleNamespace(title="OnlyTitle")
        d = sr.to_debug_dict()

        self.assertIn("campaign", d)
        self.assertEqual(d["campaign"]["id"], camp.id)
        # title present, slug/status omitted because getattr(...) returned None
        self.assertEqual(d["campaign"]["title"], "OnlyTitle")
        self.assertNotIn("slug", d["campaign"])
        self.assertNotIn("status", d["campaign"])

    def test_to_debug_dict_skips_none_topic_attrs(self):
        # Force the related-object cache to a stub that lacks one of the looped attrs
        from types import SimpleNamespace

        t = Topic.objects.create(title="TT", slug="tt")
        sr = SiteReport.objects.create(topic=t, assets_total=2)

        sr._state.fields_cache["topic"] = SimpleNamespace(slug="only-slug")
        d = sr.to_debug_dict()

        self.assertIn("topic", d)
        self.assertEqual(d["topic"]["id"], t.id)
        # slug present, title omitted because getattr(...) returned None
        self.assertEqual(d["topic"]["slug"], "only-slug")
        self.assertNotIn("title", d["topic"])


class KeyMetricsReportTestCase(TestCase):
    def _aware(self, y, m, d, hh=12, mm=0, ss=0):
        tz = timezone.get_current_timezone()
        return timezone.make_aware(datetime(y, m, d, hh, mm, ss), tz)

    def _mk_sr(self, dt, report_name, **counters):
        sr = SiteReport.objects.create(
            report_name=report_name,
            **counters,
        )
        SiteReport.objects.filter(pk=sr.pk).update(created_on=dt)
        return SiteReport.objects.get(pk=sr.pk)

    def test_helpers(self):
        # FY math
        self.assertEqual(
            KeyMetricsReport.get_fiscal_year_for_date(date(2023, 10, 1)),
            2024,
        )
        self.assertEqual(
            KeyMetricsReport.get_fiscal_year_for_date(date(2024, 9, 30)),
            2024,
        )
        self.assertEqual(
            KeyMetricsReport.get_fiscal_quarter_for_date(date(2024, 2, 1)),
            2,
        )
        self.assertEqual(
            KeyMetricsReport.get_fiscal_quarter_for_date(date(2024, 10, 1)),
            1,
        )
        # Month bounds (leap year Feb)
        first, last = KeyMetricsReport.month_bounds(date(2024, 2, 10))
        self.assertEqual(first, date(2024, 2, 1))
        self.assertEqual(last, date(2024, 2, 29))

    def test_upsert_month_from_sitereports(self):
        # Baselines at 2023-12-31; EOM at 2024-01-31
        base_dt = self._aware(2023, 12, 31, 9, 0, 0)
        eom_dt = self._aware(2024, 1, 31, 23, 0, 0)

        # TOTAL baseline + EOM
        self._mk_sr(
            base_dt,
            SiteReport.ReportName.TOTAL,
            assets_published=100,
            assets_completed=50,
            users_activated=10,
            anonymous_transcriptions=5,
            transcriptions_saved=20,
            tag_uses=40,
        )
        self._mk_sr(
            eom_dt,
            SiteReport.ReportName.TOTAL,
            assets_published=130,
            assets_completed=70,
            users_activated=16,
            anonymous_transcriptions=8,
            transcriptions_saved=26,
            tag_uses=50,
        )

        # RETIRED_TOTAL baseline + EOM
        self._mk_sr(
            base_dt,
            SiteReport.ReportName.RETIRED_TOTAL,
            assets_published=10,
            assets_completed=5,
            users_activated=1,
            anonymous_transcriptions=2,
            transcriptions_saved=3,
            tag_uses=4,
        )
        self._mk_sr(
            eom_dt,
            SiteReport.ReportName.RETIRED_TOTAL,
            assets_published=15,
            assets_completed=8,
            users_activated=2,
            anonymous_transcriptions=3,
            transcriptions_saved=5,
            tag_uses=6,
        )

        # Daily assets_started within the month (sums to 15 + 5 = 20)
        self._mk_sr(
            self._aware(2024, 1, 10),
            SiteReport.ReportName.TOTAL,
            assets_started=10,
        )
        self._mk_sr(
            self._aware(2024, 1, 20),
            SiteReport.ReportName.TOTAL,
            assets_started=5,
        )
        self._mk_sr(
            self._aware(2024, 1, 11),
            SiteReport.ReportName.RETIRED_TOTAL,
            assets_started=3,
        )
        self._mk_sr(
            self._aware(2024, 1, 21),
            SiteReport.ReportName.RETIRED_TOTAL,
            assets_started=2,
        )

        # Upsert month
        m = KeyMetricsReport.upsert_month(year=2024, month=1)
        self.assertIsNotNone(m)
        self.assertEqual(m.fiscal_year, 2024)
        self.assertEqual(m.fiscal_quarter, 2)
        self.assertEqual(m.month, 1)

        # Deltas: see analysis; expect 35, 23, 7, 4, 8, 12 and started=20
        self.assertEqual(m.assets_published, 35)
        self.assertEqual(m.assets_completed, 23)
        self.assertEqual(m.users_activated, 7)
        self.assertEqual(m.anonymous_transcriptions, 4)
        self.assertEqual(m.transcriptions_saved, 8)
        self.assertEqual(m.tag_uses, 12)
        self.assertEqual(m.assets_started, 20)

        # __str__ + filenames
        self.assertIn("FY2024M01", str(m))
        self.assertTrue(m.csv_filename().startswith("key_metrics_monthly_fy2024"))

    def test_upsert_quarter_and_fiscal_year_rollups(self):
        # Create monthly rows for FY2024 Q2 (Jan & Feb present)
        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
            month=1,
            assets_published=10,
            assets_started=2,
            assets_completed=3,
            users_activated=5,
            anonymous_transcriptions=7,
            transcriptions_saved=11,
            tag_uses=13,
            crowd_visits=None,
            avg_visit_seconds=Decimal("10.50"),
        )
        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=date(2024, 2, 1),
            period_end=date(2024, 2, 29),
            fiscal_year=2024,
            fiscal_quarter=2,
            month=2,
            assets_published=20,
            assets_started=3,
            assets_completed=4,
            users_activated=6,
            anonymous_transcriptions=8,
            transcriptions_saved=12,
            tag_uses=14,
            # manual present in Feb only
            crowd_visits=100,
            avg_visit_seconds=None,
        )

        # Quarter upsert should sum calc fields; manual sums only when present
        q2 = KeyMetricsReport.upsert_quarter(fiscal_year=2024, fiscal_quarter=2)
        self.assertIsNotNone(q2)
        self.assertEqual(q2.assets_published, 30)
        self.assertEqual(q2.assets_started, 5)
        self.assertEqual(q2.assets_completed, 7)
        self.assertEqual(q2.users_activated, 11)
        self.assertEqual(q2.anonymous_transcriptions, 15)
        self.assertEqual(q2.transcriptions_saved, 23)
        self.assertEqual(q2.tag_uses, 27)
        # Manual: only Feb had a value, so total=100, avg from Jan only
        self.assertEqual(q2.crowd_visits, 100)
        self.assertEqual(q2.avg_visit_seconds, Decimal("10.50"))

        # Fiscal year rollup on FY2024 should equal Jan+Feb (for now)
        fy = KeyMetricsReport.upsert_fiscal_year(fiscal_year=2024)
        self.assertIsNotNone(fy)
        self.assertEqual(fy.assets_published, 30)
        self.assertEqual(fy.crowd_visits, 100)
        self.assertEqual(fy.avg_visit_seconds, Decimal("10.50"))

        # String and filenames
        self.assertIn("FY2024 Q2", str(q2))
        self.assertTrue(q2.csv_filename().startswith("key_metrics_quarterly_fy2024"))
        self.assertIn("FY2024 Report", str(fy))
        self.assertTrue(fy.csv_filename().startswith("key_metrics_fiscal_year_fy2024"))

    def test___str___fallback_when_fields_incomplete(self):
        # QUARTERLY without fiscal_quarter so fallback label path
        q = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 4, 1),
            period_end=date(2024, 6, 30),
            fiscal_year=2024,
            fiscal_quarter=None,
        )
        s = str(q)
        self.assertIn("KeyMetricsReport QUARTERLY", s)
        self.assertIn("2024-04-01", s)
        self.assertIn("2024-06-30", s)

        # MONTHLY without month so fallback label path
        m = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=date(2024, 5, 1),
            period_end=date(2024, 5, 31),
            fiscal_year=2024,
            month=None,
        )
        s2 = str(m)
        self.assertIn("KeyMetricsReport MONTHLY", s2)

    def test_quarter_helper_edges(self):
        # Q3 and Q4 branches
        self.assertEqual(
            KeyMetricsReport.get_fiscal_quarter_for_date(date(2024, 4, 1)), 3
        )
        self.assertEqual(
            KeyMetricsReport.get_fiscal_quarter_for_date(date(2024, 7, 1)), 4
        )

    def test__format_value_for_csv_variants(self):
        rep = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.FISCAL_YEAR,
            period_start=date(2023, 10, 1),
            period_end=date(2024, 9, 30),
            fiscal_year=2024,
        )

        self.assertEqual(rep._format_value_for_csv("crowd_visits", None), "")

        # Manual Decimal (avg_visit_seconds) to string with 2 decimals
        self.assertEqual(
            rep._format_value_for_csv("avg_visit_seconds", Decimal("10")),
            "10.00",
        )

        self.assertEqual(rep._format_value_for_csv("crowd_visits", 0), 0)

        self.assertEqual(rep._format_value_for_csv("assets_started", None), 0)

        # Unknown field fallback: None to "", non-None to value passthrough
        self.assertEqual(rep._format_value_for_csv("unknown_field", None), "")
        self.assertEqual(rep._format_value_for_csv("unknown_field", "x"), "x")

    def test_upsert_month_returns_none_when_no_snapshots(self):
        out = KeyMetricsReport.upsert_month(year=2025, month=6)
        self.assertIsNone(out)

    def test_upsert_quarter_invalid_quarter_raises(self):
        with self.assertRaises(ValueError):
            KeyMetricsReport.upsert_quarter(fiscal_year=2024, fiscal_quarter=5)

    def test_quarter_month_specs_all_quarters(self):
        # Q1
        q1 = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2023, 10, 1),
            period_end=date(2023, 12, 31),
            fiscal_year=2024,
            fiscal_quarter=1,
        )
        self.assertEqual(
            q1._quarter_month_specs(), [(2023, 10), (2023, 11), (2023, 12)]
        )

        # Q3
        q3 = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 4, 1),
            period_end=date(2024, 6, 30),
            fiscal_year=2024,
            fiscal_quarter=3,
        )
        self.assertEqual(q3._quarter_month_specs(), [(2024, 4), (2024, 5), (2024, 6)])

        # Q4
        q4 = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 7, 1),
            period_end=date(2024, 9, 30),
            fiscal_year=2024,
            fiscal_quarter=4,
        )
        self.assertEqual(q4._quarter_month_specs(), [(2024, 7), (2024, 8), (2024, 9)])

    def test_month_bounds_handles_december(self):
        first, last = KeyMetricsReport.month_bounds(date(2024, 12, 10))
        self.assertEqual(first, date(2024, 12, 1))
        self.assertEqual(last, date(2024, 12, 31))

    def test__monthly_from_sitereports_returns_empty_dict_when_no_eom(self):
        vals = KeyMetricsReport._monthly_from_sitereports(
            month_start=date(2030, 5, 1),
            month_end=date(2030, 5, 31),
        )
        self.assertEqual(vals, {})  # no snapshots at all

    def test__monthly_from_sitereports_baseline_fallback_inside_month(self):
        # No snapshots before month start; first snapshot inside the month
        start = date(2024, 3, 1)
        end = date(2024, 3, 31)

        # TOTAL: baseline inside month (10) -> EOM (15)
        self._mk_sr(
            self._aware(2024, 3, 5, 9, 0, 0),
            SiteReport.ReportName.TOTAL,
            assets_published=10,
        )
        self._mk_sr(
            self._aware(2024, 3, 31, 23, 0, 0),
            SiteReport.ReportName.TOTAL,
            assets_published=15,
        )

        # RETIRED: baseline inside month (4) -> EOM (7)
        self._mk_sr(
            self._aware(2024, 3, 10, 9, 0, 0),
            SiteReport.ReportName.RETIRED_TOTAL,
            assets_published=4,
        )
        self._mk_sr(
            self._aware(2024, 3, 31, 23, 0, 0),
            SiteReport.ReportName.RETIRED_TOTAL,
            assets_published=7,
        )

        vals = KeyMetricsReport._monthly_from_sitereports(
            month_start=start, month_end=end
        )
        # delta should be (15+7) - (10+4) = 8
        self.assertEqual(vals["assets_published"], 8)

    def test__monthly_from_sitereports_treats_missing_series_as_zero(self):
        # Only TOTAL snapshots; RETIRED series absent
        start = date(2024, 4, 1)
        end = date(2024, 4, 30)

        # baseline inside month (100) -> EOM (110)
        self._mk_sr(
            self._aware(2024, 4, 5, 9, 0, 0),
            SiteReport.ReportName.TOTAL,
            assets_published=100,
        )
        self._mk_sr(
            self._aware(2024, 4, 30, 23, 0, 0),
            SiteReport.ReportName.TOTAL,
            assets_published=110,
        )

        vals = KeyMetricsReport._monthly_from_sitereports(
            month_start=start, month_end=end
        )
        # RETIRED contributes 0 via the helper that treats None as 0
        self.assertEqual(vals["assets_published"], 10)

    def test_upsert_quarter_returns_none_when_no_monthlies_all_quarters(self):
        # Q1
        out1 = KeyMetricsReport.upsert_quarter(fiscal_year=2027, fiscal_quarter=1)
        self.assertIsNone(out1)
        # Q3
        out3 = KeyMetricsReport.upsert_quarter(fiscal_year=2027, fiscal_quarter=3)
        self.assertIsNone(out3)
        # Q4
        out4 = KeyMetricsReport.upsert_quarter(fiscal_year=2027, fiscal_quarter=4)
        self.assertIsNone(out4)

    def test_upsert_fiscal_year_returns_none_when_no_monthlies(self):
        out = KeyMetricsReport.upsert_fiscal_year(fiscal_year=2029)
        self.assertIsNone(out)

    def test__calendar_year_for_month_in_fy_helper(self):
        rep = KeyMetricsReport(
            period_type=KeyMetricsReport.PeriodType.FISCAL_YEAR,
            period_start=date(2023, 10, 1),
            period_end=date(2024, 9, 30),
            fiscal_year=2024,
        )
        # Oct in FY should map to previous calendar year
        self.assertEqual(rep._calendar_year_for_month_in_fy(10, 2024), 2023)
        # Jun in FY maps to the FY year
        self.assertEqual(rep._calendar_year_for_month_in_fy(6, 2024), 2024)

    def test_quarter_month_specs_q2(self):
        q2 = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
        )
        self.assertEqual(q2._quarter_month_specs(), [(2024, 1), (2024, 2), (2024, 3)])


class KeyMetricsReportCsvTestCase(TestCase):
    def setUp(self):
        # FY2023 FY row (for lifetime math)
        self.fy23 = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.FISCAL_YEAR,
            period_start=date(2022, 10, 1),
            period_end=date(2023, 9, 30),
            fiscal_year=2023,
            assets_published=50,
            assets_started=5,
            assets_completed=7,
            users_activated=11,
            anonymous_transcriptions=13,
            transcriptions_saved=17,
            tag_uses=19,
            crowd_visits=30,
            avg_visit_seconds=Decimal("9.00"),
        )

        # FY2024 Q1 (for quarterly lifetime math on Q2)
        self.q1_24 = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2023, 10, 1),
            period_end=date(2023, 12, 31),
            fiscal_year=2024,
            fiscal_quarter=1,
            assets_published=7,
            assets_started=1,
            assets_completed=2,
            users_activated=3,
            anonymous_transcriptions=4,
            transcriptions_saved=5,
            tag_uses=6,
            crowd_visits=None,
            avg_visit_seconds=Decimal("8.00"),
        )

        # FY2024 monthly rows for Q2: Jan, Feb present only
        self.jan24 = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
            fiscal_year=2024,
            fiscal_quarter=2,
            month=1,
            assets_published=10,
            assets_started=2,
            assets_completed=3,
            users_activated=5,
            anonymous_transcriptions=7,
            transcriptions_saved=11,
            tag_uses=13,
            crowd_visits=None,
        )
        self.feb24 = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=date(2024, 2, 1),
            period_end=date(2024, 2, 29),
            fiscal_year=2024,
            fiscal_quarter=2,
            month=2,
            assets_published=20,
            assets_started=3,
            assets_completed=4,
            users_activated=6,
            anonymous_transcriptions=8,
            transcriptions_saved=12,
            tag_uses=14,
            crowd_visits=100,
        )

        # Upsert Q2 and FY2024 so we can render CSVs with proper totals
        self.q2_24 = KeyMetricsReport.upsert_quarter(
            fiscal_year=2024,
            fiscal_quarter=2,
        )
        self.fy24 = KeyMetricsReport.upsert_fiscal_year(fiscal_year=2024)

    def _csv_as_lines(self, rep: KeyMetricsReport) -> list[list[str]]:
        raw = rep.render_csv().decode("utf-8")
        return [line.split(",") for line in raw.strip().splitlines()]

    def test_monthly_csv_headers_and_values(self):
        # Build a synthetic single-month report to test header label only
        m = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=date(2024, 6, 1),
            period_end=date(2024, 6, 30),
            fiscal_year=2024,
            fiscal_quarter=3,
            month=6,
            assets_published=1,
        )
        lines = self._csv_as_lines(m)
        # Header: "Metric", "<Month name only>"
        self.assertEqual(lines[0][0], "Metric")
        self.assertEqual(lines[0][1], "June")

        # One known metric row check
        labels = [row[0] for row in lines[1:]]
        vals = [row[1] for row in lines[1:]]
        pub_idx = labels.index("Assets published")
        self.assertEqual(int(vals[pub_idx]), 1)

    def test_quarterly_csv_headers_totals_and_lifetime(self):
        lines = self._csv_as_lines(self.q2_24)
        header = lines[0]

        # Months present (Jan, Feb), then "FY24 Q2 totals", "FY24 Lifetime totals"
        self.assertEqual(header[0], "Metric")
        self.assertIn("January", header)
        self.assertIn("February", header)
        self.assertIn("FY24 Q2 totals", header)
        self.assertIn("FY24 Lifetime totals", header)

        # Assets published row:
        # Jan(10), Feb(20) => quarter total=30
        # Lifetime = FY2023 FY(50) + FY2024 Q1(7) = 57
        labels = [row[0] for row in lines[1:]]
        ap_idx = labels.index("Assets published")
        row = lines[1 + ap_idx]
        # [label, Jan, Feb, Q2 total, Lifetime]
        self.assertEqual(int(row[1]), 10)
        self.assertEqual(int(row[2]), 20)
        self.assertEqual(int(row[3]), 30)
        self.assertEqual(int(row[4]), 57)

        # Manual example (Crowd.loc.gov visits):
        # Jan(None), Feb(100) => Q2 total=100 (not blank)
        # Lifetime = FY2023 FY(30) + Q1(None) => 30
        cv_idx = labels.index("Crowd.loc.gov visits")
        row2 = lines[1 + cv_idx]
        self.assertEqual(row2[1], "")  # January empty
        self.assertEqual(int(row2[2]), 100)
        self.assertEqual(int(row2[3]), 100)
        self.assertEqual(int(row2[4]), 30)

    def test_fiscal_year_csv_headers_totals_and_lifetime(self):
        # Ensure FY rows exist for lifetime (FY2023 and FY2024 already present)
        lines = self._csv_as_lines(self.fy24)
        header = lines[0]

        # Header pattern:
        # Metric | (FY24 Q1 totals if present) | Q2 totals | Q3 totals? | Q4 totals?
        # | FY24 totals | FY24 Lifetime totals
        self.assertEqual(header[0], "Metric")
        self.assertIn("FY24 Q1 totals", header)
        self.assertIn("Q2 totals", header)
        self.assertIn("FY24 totals", header)
        self.assertIn("FY24 Lifetime totals", header)

        labels = [row[0] for row in lines[1:]]
        ap_idx = labels.index("Assets published")
        row = lines[1 + ap_idx]

        # With our setup:
        # Q1 assets_published=7 (preset), Q2=30 (from jan+feb),
        # year total = 37, lifetime = FY2023 FY(50) + FY2024 FY(37) = 87
        # Header columns could be: Metric, FY24 Q1 totals, Q2 totals,
        # FY24 totals, FY24 Lifetime totals (Q3/Q4 absent)
        # Find indices dynamically.
        h = header
        q1_i = h.index("FY24 Q1 totals")
        q2_i = h.index("Q2 totals")
        yt_i = h.index("FY24 totals")
        lt_i = h.index("FY24 Lifetime totals")

        self.assertEqual(int(row[q1_i]), 7)
        self.assertEqual(int(row[q2_i]), 30)
        self.assertEqual(int(row[yt_i]), 37)
        expected_lifetime = self.fy23.assets_published + self.fy24.assets_published
        self.assertEqual(int(row[lt_i]), expected_lifetime)

    def test_str_formats(self):
        # Monthly string covers Oct (calendar year is fy-1)
        oct_row = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.MONTHLY,
            period_start=date(2023, 10, 1),
            period_end=date(2023, 10, 31),
            fiscal_year=2024,
            fiscal_quarter=1,
            month=10,
        )
        s = str(oct_row)
        self.assertIn("FY2024M10", s)
        self.assertIn("(October 2023)", s)

    def test_quarterly_csv_when_no_monthlies_and_no_priors(self):
        # Create a standalone quarterly row with no monthly rows in that quarter
        q = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2019, 10, 1),
            period_end=date(2019, 12, 31),
            fiscal_year=2020,
            fiscal_quarter=1,
        )
        lines = self._csv_as_lines(q)

        # Header should be: Metric | FY25 Q3 totals | FY25 Lifetime totals
        self.assertEqual(lines[0][0], "Metric")
        self.assertIn("FY20 Q1 totals", lines[0])
        self.assertIn("FY20 Lifetime totals", lines[0])
        self.assertEqual(len(lines[0]), 3)

        labels = [r[0] for r in lines[1:]]
        # Calculated field: totals are numeric, lifetime is 0
        ap_i = labels.index("Assets published")
        ap_row = lines[1 + ap_i]
        self.assertEqual(int(ap_row[1]), 0)  # quarter total
        self.assertEqual(int(ap_row[2]), 0)  # lifetime total

        # Manual field: totals should be blank when no values
        cv_i = labels.index("Crowd.loc.gov visits")
        cv_row = lines[1 + cv_i]
        self.assertEqual(cv_row[1], "")  # quarter total blank
        self.assertEqual(cv_row[2], "")  # lifetime total blank

    def test_fiscal_year_csv_headers_when_q1_missing(self):
        # Create an FY row and only Q2 and Q4 quarters for that FY
        fy = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.FISCAL_YEAR,
            period_start=date(2025, 10, 1),
            period_end=date(2026, 9, 30),
            fiscal_year=2026,
        )
        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 3, 31),
            fiscal_year=2026,
            fiscal_quarter=2,
            assets_published=12,
        )
        KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.QUARTERLY,
            period_start=date(2026, 7, 1),
            period_end=date(2026, 9, 30),
            fiscal_year=2026,
            fiscal_quarter=4,
            assets_published=8,
        )

        lines = self._csv_as_lines(fy)
        header = lines[0]

        self.assertEqual(header[0], "Metric")
        self.assertNotIn("FY26 Q1 totals", header)
        self.assertIn("Q2 totals", header)
        self.assertNotIn("Q3 totals", header)
        self.assertIn("Q4 totals", header)
        self.assertIn("FY26 totals", header)
        self.assertIn("FY26 Lifetime totals", header)

        labels = [r[0] for r in lines[1:]]
        ap_i = labels.index("Assets published")
        row = lines[1 + ap_i]

        q2_i = header.index("Q2 totals")
        q4_i = header.index("Q4 totals")
        yt_i = header.index("FY26 totals")
        lt_i = header.index("FY26 Lifetime totals")

        self.assertEqual(int(row[q2_i]), 12)
        self.assertEqual(int(row[q4_i]), 8)
        self.assertEqual(int(row[yt_i]), 20)

        # Lifetime sums all FY rows <= 2026 (FY2023 + FY2024 + FY2026)
        expected_lifetime = (
            self.fy23.assets_published + self.fy24.assets_published + 0
        )  # FY2026 FY row has no stored value in this test
        self.assertEqual(int(row[lt_i]), expected_lifetime)

    def test_format_value_for_csv_non_decimal_avg(self):
        rep = KeyMetricsReport.objects.create(
            period_type=KeyMetricsReport.PeriodType.FISCAL_YEAR,
            period_start=date(2025, 10, 1),
            period_end=date(2026, 9, 30),
            fiscal_year=2026,
        )
        self.assertEqual(
            rep._format_value_for_csv("avg_visit_seconds", 12.3),
            "12.3",
        )
