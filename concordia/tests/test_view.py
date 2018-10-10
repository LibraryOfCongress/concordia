from datetime import datetime, timedelta

from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from concordia.models import AssetTranscriptionReservation, User
from concordia.views import get_anonymous_user

from .utils import create_asset, create_campaign, create_item, create_project


class ConcordiaViewTests(TestCase):
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

    def test_ConcordiaItemView_get(self):
        """
        Test GET on route /campaigns/<campaign-slug>/<project-slug>/<item-slug>
        """
        i = create_item()

        response = self.client.get(
            reverse(
                "transcriptions:item",
                args=(i.project.campaign.slug, i.project.slug, i.item_id),
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="transcriptions/item.html")
        self.assertContains(response, i.title)

    def test_ConcordiaAssetView_get(self):
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


class TransactionalViewTests(TransactionTestCase):
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
