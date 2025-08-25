from django.core.cache import caches
from django.db.models.signals import post_save
from django.test import (
    TransactionTestCase,
    override_settings,
)
from django.urls import reverse
from django.utils.timezone import now

from concordia.models import (
    Asset,
    Transcription,
    TranscriptionStatus,
)
from concordia.signals.handlers import on_transcription_save
from concordia.utils import get_anonymous_user
from configuration.models import Configuration

from .utils import (
    CreateTestUsers,
    JSONAssertMixin,
    create_asset,
    create_transcription,
)


@override_settings(
    RATELIMIT_ENABLE=False, SESSION_ENGINE="django.contrib.sessions.backends.cache"
)
class ReviewTranscriptionViewTests(
    CreateTestUsers, JSONAssertMixin, TransactionTestCase
):
    def test_transcription_review(self):
        asset = create_asset()

        anon = get_anonymous_user()

        t1 = Transcription(asset=asset, user=anon, text="test", submitted=now())
        t1.full_clean()
        t1.save()

        self.login_user()

        resp = self.client.post(
            reverse("review-transcription", args=(t1.pk,)), data={"action": "foobar"}
        )
        data = self.assertValidJSON(resp, expected_status=400)
        self.assertIn("error", data)

        self.assertEqual(
            1, Transcription.objects.filter(pk=t1.pk, accepted__isnull=True).count()
        )

        resp = self.client.post(
            reverse("review-transcription", args=(t1.pk,)), data={"action": "accept"}
        )
        data = self.assertValidJSON(resp, expected_status=200)

        self.assertEqual(
            1, Transcription.objects.filter(pk=t1.pk, accepted__isnull=False).count()
        )

    def test_transcription_review_rate_limit(self):
        for cache in caches.all():
            cache.clear()
        anon = get_anonymous_user()
        self.login_user()
        try:
            config = Configuration.objects.get(key="review_rate_limit")
            config.value = "4"
            config.data_type = Configuration.DataType.NUMBER
            config.save()
        except Configuration.DoesNotExist:
            Configuration.objects.create(
                key="review_rate_limit",
                value="4",
                data_type=Configuration.DataType.NUMBER,
            )

        Configuration.objects.get_or_create(
            key="review_rate_limit_popup_message",
            defaults={
                "value": "Test message",
                "data_type": Configuration.DataType.HTML,
            },
        )
        Configuration.objects.get_or_create(
            key="review_rate_limit_popup_title",
            defaults={
                "value": "Test message",
                "data_type": Configuration.DataType.HTML,
            },
        )
        Configuration.objects.get_or_create(
            key="review_rate_limit_banner_message",
            defaults={
                "value": "Test message",
                "data_type": Configuration.DataType.HTML,
            },
        )

        asset = create_asset()
        t1 = create_transcription(user=anon, asset=asset)
        t2 = create_transcription(
            user=anon, asset=create_asset(item=asset.item, slug="test-asset-2")
        )
        t3 = create_transcription(
            user=anon, asset=create_asset(item=asset.item, slug="test-asset-3")
        )
        t4 = create_transcription(
            user=anon, asset=create_asset(item=asset.item, slug="test-asset-4")
        )
        t5 = create_transcription(
            user=anon, asset=create_asset(item=asset.item, slug="test-asset-5")
        )

        resp = self.client.post(
            reverse("review-transcription", args=(t1.pk,)), data={"action": "accept"}
        )
        self.assertValidJSON(resp, expected_status=200)

        resp = self.client.post(
            reverse("review-transcription", args=(t2.pk,)), data={"action": "accept"}
        )
        self.assertValidJSON(resp, expected_status=200)

        resp = self.client.post(
            reverse("review-transcription", args=(t3.pk,)), data={"action": "accept"}
        )
        self.assertValidJSON(resp, expected_status=200)

        resp = self.client.post(
            reverse("review-transcription", args=(t4.pk,)), data={"action": "accept"}
        )
        self.assertValidJSON(resp, expected_status=200)

        resp = self.client.post(
            reverse("review-transcription", args=(t5.pk,)), data={"action": "accept"}
        )
        data = self.assertValidJSON(resp, expected_status=429)
        self.assertIn("error", data)

    def test_transcription_review_rate_limit_superuser(self):
        for cache in caches.all():
            cache.clear()
        anon = get_anonymous_user()
        self.user = self.create_super_user()
        self.login_user()
        try:
            config = Configuration.objects.get(key="review_rate_limit")
            config.value = "4"
            config.data_type = Configuration.DataType.NUMBER
            config.save()
        except Configuration.DoesNotExist:
            Configuration.objects.create(
                key="review_rate_limit",
                value="4",
                data_type=Configuration.DataType.NUMBER,
            )

        Configuration.objects.get_or_create(
            key="review_rate_limit_popup_message",
            defaults={
                "value": "Test message",
                "data_type": Configuration.DataType.HTML,
            },
        )
        Configuration.objects.get_or_create(
            key="review_rate_limit_popup_title",
            defaults={
                "value": "Test message",
                "data_type": Configuration.DataType.HTML,
            },
        )
        Configuration.objects.get_or_create(
            key="review_rate_limit_banner_message",
            defaults={
                "value": "Test message",
                "data_type": Configuration.DataType.HTML,
            },
        )

        asset = create_asset()
        t1 = create_transcription(user=anon, asset=asset)
        t2 = create_transcription(
            user=anon, asset=create_asset(item=asset.item, slug="test-asset-2")
        )
        t3 = create_transcription(
            user=anon, asset=create_asset(item=asset.item, slug="test-asset-3")
        )
        t4 = create_transcription(
            user=anon, asset=create_asset(item=asset.item, slug="test-asset-4")
        )
        t5 = create_transcription(
            user=anon, asset=create_asset(item=asset.item, slug="test-asset-5")
        )

        resp = self.client.post(
            reverse("review-transcription", args=(t1.pk,)), data={"action": "accept"}
        )
        self.assertValidJSON(resp, expected_status=200)

        resp = self.client.post(
            reverse("review-transcription", args=(t2.pk,)), data={"action": "accept"}
        )
        self.assertValidJSON(resp, expected_status=200)

        resp = self.client.post(
            reverse("review-transcription", args=(t3.pk,)), data={"action": "accept"}
        )
        self.assertValidJSON(resp, expected_status=200)

        resp = self.client.post(
            reverse("review-transcription", args=(t4.pk,)), data={"action": "accept"}
        )
        self.assertValidJSON(resp, expected_status=200)

        resp = self.client.post(
            reverse("review-transcription", args=(t5.pk,)), data={"action": "accept"}
        )
        self.assertValidJSON(resp, expected_status=200)

    def test_transcription_review_asset_status_updates(self):
        """
        Confirm that the Asset.transcription_status field is correctly updated
        throughout the review process
        """
        asset = create_asset()

        anon = get_anonymous_user()

        # We should see NOT_STARTED only when no transcription records exist:
        self.assertEqual(asset.transcription_set.count(), 0)
        self.assertEqual(
            Asset.objects.get(pk=asset.pk).transcription_status,
            TranscriptionStatus.NOT_STARTED,
        )

        t1 = Transcription(asset=asset, user=anon, text="test", submitted=now())
        t1.full_clean()
        t1.save()

        self.assertEqual(
            Asset.objects.get(pk=asset.pk).transcription_status,
            TranscriptionStatus.SUBMITTED,
        )

        # “Login” so we can review the anonymous transcription:
        self.login_user()

        self.assertEqual(
            1, Transcription.objects.filter(pk=t1.pk, accepted__isnull=True).count()
        )

        resp = self.client.post(
            reverse("review-transcription", args=(t1.pk,)), data={"action": "reject"}
        )
        self.assertValidJSON(resp, expected_status=200)

        # After rejecting a transcription, the asset status should be reset to
        # in-progress:
        self.assertEqual(
            1,
            Transcription.objects.filter(
                pk=t1.pk, accepted__isnull=True, rejected__isnull=False
            ).count(),
        )
        self.assertEqual(
            Asset.objects.get(pk=asset.pk).transcription_status,
            TranscriptionStatus.IN_PROGRESS,
        )

        # We'll simulate a second attempt:

        t2 = Transcription(
            asset=asset, user=anon, text="test", submitted=now(), supersedes=t1
        )
        t2.full_clean()
        t2.save()

        self.assertEqual(
            Asset.objects.get(pk=asset.pk).transcription_status,
            TranscriptionStatus.SUBMITTED,
        )

        resp = self.client.post(
            reverse("review-transcription", args=(t2.pk,)), data={"action": "accept"}
        )
        self.assertValidJSON(resp, expected_status=200)

        self.assertEqual(
            1, Transcription.objects.filter(pk=t2.pk, accepted__isnull=False).count()
        )
        self.assertEqual(
            Asset.objects.get(pk=asset.pk).transcription_status,
            TranscriptionStatus.COMPLETED,
        )

    def test_transcription_disallow_self_review(self):
        asset = create_asset()

        self.login_user()

        t1 = Transcription(asset=asset, user=self.user, text="test", submitted=now())
        t1.full_clean()
        t1.save()

        resp = self.client.post(
            reverse("review-transcription", args=(t1.pk,)), data={"action": "accept"}
        )
        data = self.assertValidJSON(resp, expected_status=400)
        self.assertIn("error", data)
        self.assertEqual("You cannot accept your own transcription", data["error"])

    def test_transcription_allow_self_reject(self):
        asset = create_asset()

        self.login_user()

        t1 = Transcription(asset=asset, user=self.user, text="test", submitted=now())
        t1.full_clean()
        t1.save()

        resp = self.client.post(
            reverse("review-transcription", args=(t1.pk,)), data={"action": "reject"}
        )
        self.assertValidJSON(resp, expected_status=200)
        self.assertEqual(
            Asset.objects.get(pk=asset.pk).transcription_status,
            TranscriptionStatus.IN_PROGRESS,
        )
        self.assertEqual(Transcription.objects.get(pk=t1.pk).reviewed_by, self.user)

    def test_transcription_double_review(self):
        asset = create_asset()

        anon = get_anonymous_user()

        t1 = Transcription(asset=asset, user=anon, text="test", submitted=now())
        t1.full_clean()
        t1.save()

        self.login_user()

        resp = self.client.post(
            reverse("review-transcription", args=(t1.pk,)), data={"action": "accept"}
        )
        data = self.assertValidJSON(resp, expected_status=200)

        resp = self.client.post(
            reverse("review-transcription", args=(t1.pk,)), data={"action": "reject"}
        )
        data = self.assertValidJSON(resp, expected_status=400)
        self.assertIn("error", data)
        self.assertEqual("This transcription has already been reviewed", data["error"])

    def tearDown(self):
        # We'll test the signal handler separately
        post_save.connect(on_transcription_save, sender=Transcription)
