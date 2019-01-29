from datetime import datetime, timedelta

from captcha.models import CaptchaStore
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils.timezone import now

from concordia.models import (
    Asset,
    AssetTranscriptionReservation,
    SimplePage,
    Transcription,
    TranscriptionStatus,
    User,
)
from concordia.utils import get_anonymous_user

from .utils import (
    JSONAssertMixin,
    create_asset,
    create_campaign,
    create_item,
    create_project,
)


class ConcordiaViewTests(JSONAssertMixin, TestCase):
    """
    This class contains the unit tests for the view in the concordia app.
    """

    def login_user(self):
        """
        Create a user and log the user in
        """

        # create user and login
        self.user = User.objects.create_user(
            username="tester", email="tester@example.com"
        )
        self.user.set_password("top_secret")
        self.user.save()

        self.client.login(username="tester", password="top_secret")

    def test_AccountProfileView_get(self):
        """
        Test the http GET on route account/profile
        """

        self.login_user()

        response = self.client.get(reverse("user-profile"))

        # validate the web page has the "tester" and "tester@example.com" as values
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="account/profile.html")

    def test_AccountProfileView_post(self):
        """
        This unit test tests the post entry for the route account/profile
        :param self:
        """
        test_email = "tester@example.com"

        self.login_user()

        response = self.client.post(
            reverse("user-profile"), {"email": test_email, "username": "tester"}
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("user-profile"))

        # Verify the User was correctly updated
        updated_user = User.objects.get(email=test_email)
        self.assertEqual(updated_user.email, test_email)

    def test_AccountProfileView_post_invalid_form(self):
        """
        This unit test tests the post entry for the route account/profile but
        submits an invalid form
        """
        self.login_user()

        response = self.client.post(reverse("user-profile"), {"first_name": "Jimmy"})

        self.assertEqual(response.status_code, 200)

        # Verify the User was not changed
        updated_user = User.objects.get(id=self.user.id)
        self.assertEqual(updated_user.first_name, "")

    def test_campaign_list_view(self):
        """
        Test the GET method for route /campaigns
        """
        response = self.client.get(reverse("transcriptions:campaign-list"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/campaign_list.html"
        )

        # TODO: insert campaign and test its presence

    def test_campaign_detail_view(self):
        """
        Test GET on route /campaigns/<slug-value> (campaign)
        """
        c = create_campaign(title="GET Campaign", slug="get-campaign")

        response = self.client.get(
            reverse("transcriptions:campaign-detail", args=(c.slug,))
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/campaign_detail.html"
        )
        self.assertContains(response, c.title)

    def test_concordiaCampaignView_get_page2(self):
        """
        Test GET on route /campaigns/<slug-value>/ (campaign) on page 2
        """
        c = create_campaign()

        response = self.client.get(
            reverse("transcriptions:campaign-detail", args=(c.slug,)), {"page": 2}
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/campaign_detail.html"
        )

    def test_empty_item_detail_view(self):
        """
        Test item detail display with no assets
        """

        item = create_item()

        response = self.client.get(
            reverse(
                "transcriptions:item-detail",
                args=(item.project.campaign.slug, item.project.slug, item.item_id),
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/item_detail.html"
        )
        self.assertContains(response, item.title)

        self.assertEqual(0, response.context["not_started_percent"])
        self.assertEqual(0, response.context["in_progress_percent"])
        self.assertEqual(0, response.context["submitted_percent"])
        self.assertEqual(0, response.context["completed_percent"])

    def test_item_detail_view(self):
        """
        Test item detail display with assets
        """

        self.login_user()  # Implicitly create the test account
        anon = get_anonymous_user()

        item = create_item()
        # We'll create 10 assets and transcriptions for some of them so we can
        # confirm that the math is working correctly:
        for i in range(1, 11):
            asset = create_asset(item=item, sequence=i, slug=f"test-{i}")
            if i > 9:
                t = asset.transcription_set.create(asset=asset, user=anon)
                t.submitted = now()
                t.accepted = now()
                t.reviewed_by = self.user
            elif i > 7:
                t = asset.transcription_set.create(asset=asset, user=anon)
                t.submitted = now()
            elif i > 4:
                t = asset.transcription_set.create(asset=asset, user=anon)
            else:
                continue

            t.full_clean()
            t.save()

        response = self.client.get(
            reverse(
                "transcriptions:item-detail",
                args=(item.project.campaign.slug, item.project.slug, item.item_id),
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/item_detail.html"
        )
        self.assertContains(response, item.title)

        # We have 10 total, 6 of which have transcription records and of those
        # 6, 3 have been submitted and one of those was accepted:
        self.assertEqual(40, response.context["not_started_percent"])
        self.assertEqual(30, response.context["in_progress_percent"])
        self.assertEqual(20, response.context["submitted_percent"])
        self.assertEqual(10, response.context["completed_percent"])

    def test_asset_detail_view(self):
        """
        This unit test test the GET route /campaigns/<campaign>/asset/<Asset_name>/
        with already in use.
        """
        self.login_user()

        asset = create_asset()

        self.transcription = asset.transcription_set.create(
            user_id=self.user.id, text="Test transcription 1"
        )
        self.transcription.save()

        response = self.client.get(
            reverse(
                "transcriptions:asset-detail",
                kwargs={
                    "campaign_slug": asset.item.project.campaign.slug,
                    "project_slug": asset.item.project.slug,
                    "item_id": asset.item.item_id,
                    "slug": asset.slug,
                },
            )
        )

        self.assertEqual(response.status_code, 200)

    def test_project_detail_view(self):
        """
        Test GET on route /campaigns/<slug-value> (campaign)
        """
        project = create_project()

        response = self.client.get(
            reverse(
                "transcriptions:project-detail",
                args=(project.campaign.slug, project.slug),
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/project_detail.html"
        )

    def test_campaign_report(self):
        """
        Test campaign reporting
        """

        item = create_item()
        # We'll create 10 assets and transcriptions for some of them so we can
        # confirm that the math is working correctly:
        for i in range(1, 11):
            create_asset(item=item, sequence=i, slug=f"test-{i}")

        response = self.client.get(
            reverse(
                "transcriptions:campaign-report",
                kwargs={"campaign_slug": item.project.campaign.slug},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "transcriptions/campaign_report.html")

        ctx = response.context

        self.assertEqual(ctx["title"], item.project.campaign.title)
        self.assertEqual(ctx["total_asset_count"], 10)

    def test_simple_page(self):
        s = SimplePage.objects.create(
            title="Help Center 123",
            body="not the real body",
            path=reverse("help-center"),
        )

        resp = self.client.get(reverse("help-center"))
        self.assertEqual(200, resp.status_code)
        self.assertEqual(s.title, resp.context["title"])
        self.assertEqual(
            [(reverse("help-center"), s.title)], resp.context["breadcrumbs"]
        )
        self.assertEqual(resp.context["body"], f"<p>{s.body}</p>")

    def test_ajax_session_status_anon(self):
        resp = self.client.get(reverse("ajax-session-status"))
        data = self.assertValidJSON(resp)
        self.assertEqual(data, {})

    def test_ajax_session_status(self):
        self.login_user()

        resp = self.client.get(reverse("ajax-session-status"))
        data = self.assertValidJSON(resp)

        self.assertIn("links", data)
        self.assertIn("username", data)

        self.assertEqual(data["username"], self.user.username)

        self.assertIn("private", resp["Cache-Control"])

    def test_ajax_messages(self):
        self.login_user()

        resp = self.client.get(reverse("ajax-messages"))
        data = self.assertValidJSON(resp)

        self.assertIn("messages", data)

        # This view cannot be cached because the messages would be displayed
        # multiple times:
        self.assertIn("no-cache", resp["Cache-Control"])


class TransactionalViewTests(JSONAssertMixin, TransactionTestCase):
    def login_user(self):
        """
        Create a user and log the user in
        """

        # create user and login
        self.user = User.objects.create_user(
            username="tester", email="tester@example.com"
        )
        self.user.set_password("top_secret")
        self.user.save()

        self.client.login(username="tester", password="top_secret")

    def completeCaptcha(self, key=None):
        """Submit a CAPTCHA response using the provided challenge key"""

        if key is None:
            challenge_data = self.assertValidJSON(
                self.client.get(reverse("ajax-captcha")), expected_status=401
            )
            self.assertIn("key", challenge_data)
            self.assertIn("image", challenge_data)
            key = challenge_data["key"]

        self.assertValidJSON(
            self.client.post(
                reverse("ajax-captcha"),
                data={
                    "key": key,
                    "response": CaptchaStore.objects.get(hashkey=key).response,
                },
            )
        )

    def test_asset_reservation(self):
        """
        Test the basic Asset reservation process
        """

        self.login_user()
        self._asset_reservation_test_payload(self.user.pk)

    def test_asset_reservation_anonymously(self):
        """
        Test the basic Asset reservation process as an anonymous user
        """

        anon_user = get_anonymous_user()
        self._asset_reservation_test_payload(anon_user.pk)

    def _asset_reservation_test_payload(self, user_id):
        asset = create_asset()

        # Acquire the reservation:
        with self.assertNumQueries(3):  # 1 auth query + 1 expiry + 1 acquire
            resp = self.client.post(
                reverse("reserve-asset-for-transcription", args=(asset.pk,))
            )
        self.assertEqual(204, resp.status_code)

        reservation = AssetTranscriptionReservation.objects.get()
        self.assertEqual(reservation.user_id, user_id)
        self.assertEqual(reservation.asset, asset)

        # Confirm that an update did not change the pk when it updated the timestamp:

        with self.assertNumQueries(3):  # 1 auth query + 1 expiry + 1 acquire
            resp = self.client.post(
                reverse("reserve-asset-for-transcription", args=(asset.pk,))
            )
        self.assertEqual(204, resp.status_code)

        self.assertEqual(1, AssetTranscriptionReservation.objects.count())
        updated_reservation = AssetTranscriptionReservation.objects.get()
        self.assertEqual(updated_reservation.user_id, user_id)
        self.assertEqual(updated_reservation.asset, asset)
        self.assertEqual(reservation.created_on, updated_reservation.created_on)
        self.assertLess(reservation.updated_on, updated_reservation.updated_on)

        # Release the reservation now that we're done:

        # 3 = 1 auth query + 1 expiry + 1 delete
        with self.assertNumQueries(3):
            resp = self.client.post(
                reverse("reserve-asset-for-transcription", args=(asset.pk,)),
                data={"release": True},
            )
        self.assertEqual(204, resp.status_code)

        self.assertEqual(0, AssetTranscriptionReservation.objects.count())

    def test_asset_reservation_competition(self):
        """
        Confirm that two users cannot reserve the same asset at the same time
        """

        asset = create_asset()

        # We'll reserve the test asset as the anonymous user and then attempt
        # to edit it after logging in

        # 4 queries = 1 auth query + 1 anonymous user creation + 1 expiry + 1 acquire
        with self.assertNumQueries(4):
            resp = self.client.post(
                reverse("reserve-asset-for-transcription", args=(asset.pk,))
            )
        self.assertEqual(204, resp.status_code)
        self.assertEqual(1, AssetTranscriptionReservation.objects.count())

        self.login_user()

        with self.assertNumQueries(3):  # 1 auth query + 1 expiry + 1 acquire
            resp = self.client.post(
                reverse("reserve-asset-for-transcription", args=(asset.pk,))
            )
        self.assertEqual(409, resp.status_code)
        self.assertEqual(1, AssetTranscriptionReservation.objects.count())

    def test_asset_reservation_expiration(self):
        """
        Simulate an expired reservation which should not cause the request to fail
        """
        asset = create_asset()

        stale_reservation = AssetTranscriptionReservation(
            user=get_anonymous_user(), asset=asset
        )
        stale_reservation.full_clean()
        stale_reservation.save()
        # Backdate the object as if it happened 15 minutes ago:
        old_timestamp = datetime.now() - timedelta(minutes=15)
        AssetTranscriptionReservation.objects.update(
            created_on=old_timestamp, updated_on=old_timestamp
        )

        self.login_user()

        with self.assertNumQueries(3):  # 1 auth query + 1 expiry + 1 acquire
            resp = self.client.post(
                reverse("reserve-asset-for-transcription", args=(asset.pk,))
            )
        self.assertEqual(204, resp.status_code)

        self.assertEqual(1, AssetTranscriptionReservation.objects.count())
        reservation = AssetTranscriptionReservation.objects.get()
        self.assertEqual(reservation.user_id, self.user.pk)

    def test_anonymous_transcription_save_captcha(self):
        asset = create_asset()

        resp = self.client.post(
            reverse("save-transcription", args=(asset.pk,)), data={"text": "test"}
        )
        data = self.assertValidJSON(resp, expected_status=401)
        self.assertIn("key", data)
        self.assertIn("image", data)

        self.completeCaptcha(data["key"])

        resp = self.client.post(
            reverse("save-transcription", args=(asset.pk,)), data={"text": "test"}
        )
        data = self.assertValidJSON(resp, expected_status=201)

    def test_transcription_save(self):
        asset = create_asset()

        # We're not testing the CAPTCHA here so we'll complete it:
        self.completeCaptcha()

        resp = self.client.post(
            reverse("save-transcription", args=(asset.pk,)), data={"text": "test"}
        )
        data = self.assertValidJSON(resp, expected_status=201)
        self.assertIn("submissionUrl", data)

        # Test attempts to create a second transcription without marking that it
        # supersedes the previous one:
        resp = self.client.post(
            reverse("save-transcription", args=(asset.pk,)), data={"text": "test"}
        )
        data = self.assertValidJSON(resp, expected_status=409)
        self.assertIn("error", data)

        # This should work with the chain specified:
        resp = self.client.post(
            reverse("save-transcription", args=(asset.pk,)),
            data={"text": "test", "supersedes": asset.transcription_set.get().pk},
        )
        data = self.assertValidJSON(resp, expected_status=201)
        self.assertIn("submissionUrl", data)

        # We should see an error if you attempt to supersede a transcription
        # which has already been superseded:
        resp = self.client.post(
            reverse("save-transcription", args=(asset.pk,)),
            data={
                "text": "test",
                "supersedes": asset.transcription_set.order_by("pk").first().pk,
            },
        )
        data = self.assertValidJSON(resp, expected_status=409)
        self.assertIn("error", data)

        # A logged in user can take over from an anonymous user:
        self.login_user()
        resp = self.client.post(
            reverse("save-transcription", args=(asset.pk,)),
            data={
                "text": "test",
                "supersedes": asset.transcription_set.order_by("pk").last().pk,
            },
        )
        data = self.assertValidJSON(resp, expected_status=201)
        self.assertIn("submissionUrl", data)

    def test_anonymous_transcription_submission(self):
        asset = create_asset()
        anon = get_anonymous_user()

        transcription = Transcription(asset=asset, user=anon, text="previous entry")
        transcription.full_clean()
        transcription.save()

        resp = self.client.post(
            reverse("submit-transcription", args=(transcription.pk,))
        )
        data = self.assertValidJSON(resp, expected_status=401)
        self.assertIn("key", data)
        self.assertIn("image", data)

        self.assertFalse(Transcription.objects.filter(submitted__isnull=False).exists())

        self.completeCaptcha(data["key"])
        self.client.post(reverse("submit-transcription", args=(transcription.pk,)))
        self.assertTrue(Transcription.objects.filter(submitted__isnull=False).exists())

    def test_transcription_submission(self):
        asset = create_asset()

        # We're not testing the CAPTCHA here so we'll complete it:
        self.completeCaptcha()

        resp = self.client.post(
            reverse("save-transcription", args=(asset.pk,)), data={"text": "test"}
        )
        data = self.assertValidJSON(resp, expected_status=201)

        transcription = Transcription.objects.get()
        self.assertEqual(None, transcription.submitted)

        resp = self.client.post(
            reverse("submit-transcription", args=(transcription.pk,))
        )
        data = self.assertValidJSON(resp, expected_status=200)
        self.assertIn("id", data)
        self.assertEqual(data["id"], transcription.pk)

        transcription = Transcription.objects.get()
        self.assertTrue(transcription.submitted)

    def test_stale_transcription_submission(self):
        asset = create_asset()

        # We're not testing the CAPTCHA here so we'll complete it:
        self.completeCaptcha()

        anon = get_anonymous_user()

        t1 = Transcription(asset=asset, user=anon, text="test")
        t1.full_clean()
        t1.save()

        t2 = Transcription(asset=asset, user=anon, text="test", supersedes=t1)
        t2.full_clean()
        t2.save()

        resp = self.client.post(reverse("submit-transcription", args=(t1.pk,)))
        data = self.assertValidJSON(resp, expected_status=400)
        self.assertIn("error", data)

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

    def test_anonymous_tag_submission(self):
        """Confirm that anonymous users cannot submit tags"""
        asset = create_asset()
        submit_url = reverse("submit-tags", kwargs={"asset_pk": asset.pk})

        resp = self.client.post(submit_url, data={"tags": ["foo", "bar"]})
        self.assertRedirects(resp, "%s?next=%s" % (reverse("login"), submit_url))

    def test_tag_submission(self):
        asset = create_asset()

        self.login_user()

        test_tags = ["foo", "bar"]

        resp = self.client.post(
            reverse("submit-tags", kwargs={"asset_pk": asset.pk}),
            data={"tags": test_tags},
        )
        data = self.assertValidJSON(resp, expected_status=200)
        self.assertIn("user_tags", data)
        self.assertIn("all_tags", data)

        self.assertEqual(sorted(test_tags), data["user_tags"])
        self.assertEqual(sorted(test_tags), data["all_tags"])

    def test_tag_submission_with_multiple_users(self):
        asset = create_asset()
        self.login_user()

        test_tags = ["foo", "bar"]

        resp = self.client.post(
            reverse("submit-tags", kwargs={"asset_pk": asset.pk}),
            data={"tags": test_tags},
        )
        data = self.assertValidJSON(resp, expected_status=200)
        self.assertIn("user_tags", data)
        self.assertIn("all_tags", data)

        self.assertEqual(sorted(test_tags), data["user_tags"])
        self.assertEqual(sorted(test_tags), data["all_tags"])

    def test_duplicate_tag_submission(self):
        """Confirm that tag values cannot be duplicated"""
        asset = create_asset()

        self.login_user()

        resp = self.client.post(
            reverse("submit-tags", kwargs={"asset_pk": asset.pk}),
            data={"tags": ["foo", "bar", "baaz"]},
        )
        data = self.assertValidJSON(resp, expected_status=200)

        second_user = User.objects.create_user(
            username="second_tester", email="second_tester@example.com"
        )
        second_user.set_password("secret")
        second_user.save()
        self.client.login(username="second_tester", password="secret")

        resp = self.client.post(
            reverse("submit-tags", kwargs={"asset_pk": asset.pk}),
            data={"tags": ["foo", "bar", "quux"]},
        )
        data = self.assertValidJSON(resp, expected_status=200)

        # Even though the user submitted (through some horrible bug) duplicate
        # values, they should not be stored:
        self.assertEqual(["bar", "foo", "quux"], data["user_tags"])
        self.assertEqual(["baaz", "bar", "foo", "quux"], data["all_tags"])

    def test_find_next_transcribable(self):
        asset1 = create_asset(slug="test-asset-1")
        asset2 = create_asset(item=asset1.item, slug="test-asset-2")
        campaign = asset1.item.project.campaign

        resp = self.client.get(
            reverse(
                "transcriptions:redirect-to-next-transcribable-asset",
                kwargs={"campaign_slug": campaign.slug},
            )
        )

        self.assertRedirects(resp, expected_url=asset2.get_absolute_url())

    def test_find_next_transcribable_single_asset(self):
        asset = create_asset()
        campaign = asset.item.project.campaign

        resp = self.client.get(
            reverse(
                "transcriptions:redirect-to-next-transcribable-asset",
                kwargs={"campaign_slug": campaign.slug},
            )
        )

        self.assertRedirects(resp, expected_url=asset.get_absolute_url())

    def test_find_next_transcribable_in_singleton_campaign(self):
        asset = create_asset(transcription_status=TranscriptionStatus.SUBMITTED)
        campaign = asset.item.project.campaign

        resp = self.client.get(
            reverse(
                "transcriptions:redirect-to-next-transcribable-asset",
                kwargs={"campaign_slug": campaign.slug},
            )
        )

        self.assertRedirects(
            resp,
            expected_url=reverse(
                "transcriptions:campaign-detail", args=(campaign.slug,)
            ),
        )

    def test_find_next_transcribable_project_redirect(self):
        asset = create_asset(transcription_status=TranscriptionStatus.SUBMITTED)
        project = asset.item.project
        campaign = project.campaign

        resp = self.client.get(
            "%s?project=%s"
            % (
                reverse(
                    "transcriptions:redirect-to-next-transcribable-asset",
                    kwargs={"campaign_slug": campaign.slug},
                ),
                project.slug,
            )
        )

        self.assertRedirects(
            resp,
            expected_url=reverse(
                "transcriptions:project-detail", args=(campaign.slug, project.slug)
            ),
        )

    def test_find_next_transcribable_hierarchy(self):
        """Confirm that find-next-page selects assets in the expected order"""

        asset = create_asset()
        item = asset.item
        project = item.project
        campaign = project.campaign

        asset_in_item = create_asset(item=item, slug="test-asset-in-same-item")
        in_progress_asset_in_item = create_asset(
            item=item,
            slug="inprogress-asset-in-same-item",
            transcription_status=TranscriptionStatus.IN_PROGRESS,
        )

        asset_in_project = create_asset(
            item=create_item(project=project, item_id="other-item-in-same-project"),
            title="test-asset-in-same-project",
        )

        asset_in_campaign = create_asset(
            item=create_item(
                project=create_project(campaign=campaign, title="other project"),
                title="item in other project",
            ),
            slug="test-asset-in-same-campaign",
        )

        # Now that we have test assets we'll see what find-next-page gives us as
        # successive test records are marked as submitted and thus ineligible.
        # The expected ordering is that it will favor moving forward (i.e. not
        # landing you on the same asset unless that's the only one available),
        # and will keep you closer to the asset you started from (i.e. within
        # the same item or project in that order).

        self.assertRedirects(
            self.client.get(
                reverse(
                    "transcriptions:redirect-to-next-transcribable-asset",
                    kwargs={"campaign_slug": campaign.slug},
                ),
                {"project": project.slug, "item": item.item_id, "asset": asset.pk},
            ),
            asset_in_item.get_absolute_url(),
        )

        asset_in_item.transcription_status = TranscriptionStatus.SUBMITTED
        asset_in_item.save()
        AssetTranscriptionReservation.objects.all().delete()

        self.assertRedirects(
            self.client.get(
                reverse(
                    "transcriptions:redirect-to-next-transcribable-asset",
                    kwargs={"campaign_slug": campaign.slug},
                ),
                {"project": project.slug, "item": item.item_id, "asset": asset.pk},
            ),
            asset_in_project.get_absolute_url(),
        )

        asset_in_project.transcription_status = TranscriptionStatus.SUBMITTED
        asset_in_project.save()
        AssetTranscriptionReservation.objects.all().delete()

        self.assertRedirects(
            self.client.get(
                reverse(
                    "transcriptions:redirect-to-next-transcribable-asset",
                    kwargs={"campaign_slug": campaign.slug},
                ),
                {"project": project.slug, "item": item.item_id, "asset": asset.pk},
            ),
            asset_in_campaign.get_absolute_url(),
        )

        asset_in_campaign.transcription_status = TranscriptionStatus.SUBMITTED
        asset_in_campaign.save()
        AssetTranscriptionReservation.objects.all().delete()

        self.assertRedirects(
            self.client.get(
                reverse(
                    "transcriptions:redirect-to-next-transcribable-asset",
                    kwargs={"campaign_slug": campaign.slug},
                ),
                {"project": project.slug, "item": item.item_id, "asset": asset.pk},
            ),
            in_progress_asset_in_item.get_absolute_url(),
        )
