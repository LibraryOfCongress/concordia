from datetime import datetime, timedelta

from captcha.models import CaptchaStore
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils.timezone import now

from concordia.models import AssetTranscriptionReservation, Transcription, User
from concordia.views import get_anonymous_user

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
        response = self.client.get(reverse("transcriptions:campaigns"))

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

        response = self.client.get(reverse("transcriptions:campaign", args=(c.slug,)))

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
            reverse("transcriptions:campaign", args=(c.slug,)), {"page": 2}
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

        self.assertEqual(0, response.context["edit_percent"])
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
        self.assertEqual(60, response.context["edit_percent"])
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
        self.assertTemplateUsed(response, template_name="transcriptions/project.html")

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

    def test_static_page(self):
        resp = self.client.get(reverse("help-center"))
        self.assertEqual(200, resp.status_code)
        self.assertEqual("Help Center", resp.context["title"])
        self.assertEqual(
            [(reverse("help-center"), "Help Center")], resp.context["breadcrumbs"]
        )
        self.assertIn("body", resp.context)


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

    def test_transcription_self_review(self):
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
        self.assertEqual("You cannot review your own transcription", data["error"])

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
