from datetime import date, timedelta
from unittest.mock import patch

from django import forms
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.test import (
    Client,
    RequestFactory,
    TestCase,
    TransactionTestCase,
    override_settings,
)
from django.urls import reverse
from django.utils.timezone import now

from concordia.models import (
    Asset,
    AssetTranscriptionReservation,
    Campaign,
    Transcription,
    TranscriptionStatus,
)
from concordia.tasks import (
    delete_old_tombstoned_reservations,
    expire_inactive_asset_reservations,
    tombstone_old_active_asset_reservations,
)
from concordia.utils import get_anonymous_user, get_or_create_reservation_token
from concordia.views import (
    AccountProfileView,
    CompletedCampaignListView,
    FilteredItemDetailView,
    FilteredProjectDetailView,
    ratelimit_view,
    registration_rate,
)

from .utils import (
    CreateTestUsers,
    JSONAssertMixin,
    create_asset,
    create_campaign,
    create_card_family,
    create_guide,
    create_item,
    create_project,
    create_topic,
    create_transcription,
)


def setup_view(view, request, user=None, *args, **kwargs):
    """
    https://stackoverflow.com/a/33647251/10320488
    """
    if user:
        request.user = user
    view.request = request
    view.args = args
    view.kwargs = kwargs
    return view


class AccountProfileViewTests(CreateTestUsers, TestCase):
    """
    This class contains the unit tests for the AccountProfileView.
    """

    def test_get_queryset(self):
        """
        Test the get_queryset method
        """
        self.login_user()
        v = setup_view(
            AccountProfileView(),
            RequestFactory().get("account/password_reset/"),
            user=self.user,
        )
        qs = v.get_queryset()
        self.assertEqual(qs.count(), 0)


class CompletedCampaignListViewTests(TestCase):
    """
    This class contains the unit tests for the CompletedCampaignListView
    """

    def setUp(self):
        today = date.today()
        self.campaign1 = create_campaign(
            published=True, status=Campaign.Status.COMPLETED, completed_date=today
        )
        yesterday = today - timedelta(days=1)
        self.campaign2 = create_campaign(
            published=True,
            status=Campaign.Status.COMPLETED,
            slug="test-campaign-2",
            completed_date=yesterday,
        )

    def test_queryset(self):
        view = CompletedCampaignListView()
        self.assertGreater(
            view.queryset.first().completed_date, view.queryset.last().completed_date
        )


@override_settings(
    RATELIMIT_ENABLE=False, SESSION_ENGINE="django.contrib.sessions.backends.cache"
)
class ConcordiaViewTests(CreateTestUsers, JSONAssertMixin, TestCase):
    """
    This class contains the unit tests for the view in the concordia app.
    """

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_ratelimit_view(self):
        c = Client()
        response = c.get("/error/429/")
        self.assertIsInstance(response, HttpResponse)
        self.assertEqual(response.status_code, 429)

        headers = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}
        response = c.get("/error/429/", **headers)
        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 429)

    def test_campaign_topic_list_view(self):
        """
        Test the GET method for route /campaigns-topics
        """
        campaign = create_campaign(title="Hello Everyone")
        topic_project = create_project(campaign=campaign)
        campaign_item = create_item(project=topic_project)
        create_asset(item=campaign_item)
        unlisted_campaign = create_campaign(
            title="Hello to only certain people", unlisted=True
        )
        unlisted_topic_project = create_project(campaign=unlisted_campaign)
        unlisted_campaign_item = create_item(project=unlisted_topic_project)
        create_asset(item=unlisted_campaign_item)
        topic = create_topic(title="A Listed Topic", project=topic_project)
        unlisted_topic = create_topic(
            title="An Unlisted Topic", unlisted=True, project=unlisted_topic_project
        )

        response = self.client.get(reverse("campaign-topic-list"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/campaign_topic_list.html"
        )
        self.assertContains(response, topic.title)
        self.assertNotContains(response, unlisted_topic.title)
        self.assertContains(response, campaign.title)
        self.assertNotContains(response, unlisted_campaign.title)

    def test_topic_list_view(self):
        """
        Test the GET method for route /topics
        """
        campaign = create_campaign(title="Hello Everyone")
        topic_project = create_project(campaign=campaign)
        unlisted_campaign = create_campaign(
            title="Hello to only certain people", unlisted=True
        )
        unlisted_topic_project = create_project(campaign=unlisted_campaign)

        topic = create_topic(title="A Listed Topic", project=topic_project)
        unlisted_topic = create_topic(
            title="An Unlisted Topic", unlisted=True, project=unlisted_topic_project
        )

        response = self.client.get(reverse("topic-list"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/topic_list.html"
        )
        self.assertContains(response, topic.title)
        self.assertNotContains(response, unlisted_topic.title)

    def test_campaign_list_view(self):
        """
        Test the GET method for route /campaigns
        """
        campaign = create_campaign(title="Hello Everyone 2")
        unlisted_campaign = create_campaign(
            title="Hello to only certain people 2", unlisted=True
        )

        response = self.client.get(reverse("transcriptions:campaign-list"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/campaign_list.html"
        )
        self.assertContains(response, campaign.title)
        self.assertNotContains(response, unlisted_campaign.title)

    def test_topic_detail_view(self):
        """
        Test GET on route /topics/<slug-value> (topic)
        """
        c = create_topic(title="GET Topic", slug="get-topic")

        response = self.client.get(reverse("topic-detail", args=(c.slug,)))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/topic_detail.html"
        )
        self.assertContains(response, c.title)

    def test_unlisted_topic_detail_view(self):
        c2 = create_topic(
            title="GET Unlisted Topic", unlisted=True, slug="get-unlisted-topic"
        )

        response2 = self.client.get(reverse("topic-detail", args=(c2.slug,)))

        self.assertEqual(response2.status_code, 200)
        self.assertTemplateUsed(
            response2, template_name="transcriptions/topic_detail.html"
        )
        self.assertContains(response2, c2.title)

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

        c2 = create_campaign(
            title="GET Unlisted Campaign", unlisted=True, slug="get-unlisted-campaign"
        )

        response2 = self.client.get(
            reverse("transcriptions:campaign-detail", args=(c2.slug,))
        )

        self.assertEqual(response2.status_code, 200)
        self.assertTemplateUsed(
            response2, template_name="transcriptions/campaign_detail.html"
        )
        self.assertContains(response2, c2.title)

    def test_campaign_unicode_slug(self):
        """Confirm that Unicode characters are usable in Campaign URLs"""

        campaign = create_campaign(title="你好 World")

        self.assertEqual(campaign.slug, "你好-world")

        response = self.client.get(campaign.get_absolute_url())

        self.assertEqual(response.status_code, 200)

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

    def test_asset_unicode_slug(self):
        """Confirm that Unicode characters are usable in Asset URLs"""

        asset = create_asset(title="你好 World")

        self.assertEqual(asset.slug, "你好-world")

        response = self.client.get(asset.get_absolute_url())

        self.assertEqual(response.status_code, 200)

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

        asset.item.project.campaign.card_family = create_card_family()
        asset.item.project.campaign.save()
        title = "Transcription: Basic Rules"
        create_guide(title=title)

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
        self.assertIn("cards", response.context)
        self.assertIn("guides", response.context)
        self.assertEqual(title, response.context["guides"][0]["title"])

    @patch.object(Asset, "get_ocr_transcript")
    def test_generate_ocr_transcription(self, mock):
        self.login_user()
        asset1 = create_asset(storage_image="tests/test-european.jpg")
        url = reverse("generate-ocr-transcription", kwargs={"asset_pk": asset1.pk})
        self.client.post(url)
        self.assertTrue(mock.called)

        asset2 = create_asset(
            item=asset1.item,
            slug="test-asset-2",
            storage_image="tests/test-european.jpg",
        )
        url = reverse("generate-ocr-transcription", kwargs={"asset_pk": asset2.pk})
        self.client.post(url, data={"language": "spa"})
        mock.assert_called_with("spa")

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

    def test_project_unicode_slug(self):
        """Confirm that Unicode characters are usable in Project URLs"""

        project = create_project(title="你好 World")

        self.assertEqual(project.slug, "你好-world")

        response = self.client.get(project.get_absolute_url())

        self.assertEqual(response.status_code, 200)

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

        response = self.client.get(
            reverse(
                "transcriptions:campaign-report",
                kwargs={"campaign_slug": item.project.campaign.slug},
            ),
            {"page": "not-an-int"},
        )

        ctx = response.context

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "transcriptions/campaign_report.html")
        self.assertEqual(ctx["projects"].number, 1)

        response = self.client.get(
            reverse(
                "transcriptions:campaign-report",
                kwargs={"campaign_slug": item.project.campaign.slug},
            ),
            {"page": 10000},
        )

        ctx = response.context
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "transcriptions/campaign_report.html")
        self.assertEqual(ctx["projects"].number, 1)


@override_settings(
    RATELIMIT_ENABLE=False, SESSION_ENGINE="django.contrib.sessions.backends.cache"
)
class TransactionalViewTests(CreateTestUsers, JSONAssertMixin, TransactionTestCase):
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
        self._asset_reservation_test_payload(anon_user.pk, anonymous=True)

    def _asset_reservation_test_payload(self, user_id, anonymous=False):
        asset = create_asset()

        # Acquire the reservation: 1 acquire
        # + 1 reservation check
        # + 1 session if not anonymous and using a database:
        expected_update_queries = 2
        if not anonymous and settings.SESSION_ENGINE.endswith("db"):
            expected_update_queries += 1
        # + 1 get user ID from request
        expected_acquire_queries = expected_update_queries + 1

        with self.assertNumQueries(expected_acquire_queries):
            resp = self.client.post(reverse("reserve-asset", args=(asset.pk,)))
        data = self.assertValidJSON(resp, expected_status=200)

        reservation = AssetTranscriptionReservation.objects.get()
        self.assertEqual(reservation.reservation_token, data["reservation_token"])
        self.assertEqual(reservation.asset, asset)

        # Confirm that an update did not change the pk when it updated the timestamp:

        with self.assertNumQueries(expected_update_queries):
            resp = self.client.post(reverse("reserve-asset", args=(asset.pk,)))
        data = self.assertValidJSON(resp, expected_status=200)
        self.assertEqual(1, AssetTranscriptionReservation.objects.count())
        updated_reservation = AssetTranscriptionReservation.objects.get()
        self.assertEqual(
            updated_reservation.reservation_token, data["reservation_token"]
        )
        self.assertEqual(updated_reservation.asset, asset)
        self.assertEqual(reservation.created_on, updated_reservation.created_on)
        self.assertLess(reservation.created_on, updated_reservation.updated_on)

        # Release the reservation now that we're done:
        # 1 release + 1 session if not anonymous and using a database:
        if not anonymous and settings.SESSION_ENGINE.endswith("db"):
            expected_release_queries = 2
        else:
            expected_release_queries = 1

        with self.assertNumQueries(expected_release_queries):
            resp = self.client.post(
                reverse("reserve-asset", args=(asset.pk,)), data={"release": True}
            )
        data = self.assertValidJSON(resp, expected_status=200)
        self.assertEqual(
            updated_reservation.reservation_token, data["reservation_token"]
        )

        self.assertEqual(0, AssetTranscriptionReservation.objects.count())

    def test_asset_reservation_competition(self):
        """
        Confirm that two users cannot reserve the same asset at the same time
        """

        asset = create_asset()

        # We'll reserve the test asset as the anonymous user and then attempt
        # to edit it after logging in

        # 4 queries =
        # 1 expiry + 1 acquire + 2 get user ID + 2 get user profile from request
        with self.assertNumQueries(6):
            resp = self.client.post(reverse("reserve-asset", args=(asset.pk,)))
        self.assertEqual(200, resp.status_code)
        self.assertEqual(1, AssetTranscriptionReservation.objects.count())

        # Clear the login session so the reservation_token will be regenerated:
        self.client.logout()
        self.login_user()

        # 1 session check + 1 acquire + get user ID from request
        with self.assertNumQueries(3 if settings.SESSION_ENGINE.endswith("db") else 2):
            resp = self.client.post(reverse("reserve-asset", args=(asset.pk,)))
        self.assertEqual(409, resp.status_code)
        self.assertEqual(1, AssetTranscriptionReservation.objects.count())

    def test_asset_reservation_expiration(self):
        """
        Simulate an expired reservation which should not cause the request to fail
        """
        asset = create_asset()

        stale_reservation = AssetTranscriptionReservation(  # nosec
            asset=asset, reservation_token="stale"
        )
        stale_reservation.full_clean()
        stale_reservation.save()
        # Backdate the object as if it happened 31 minutes ago:
        old_timestamp = now() - timedelta(minutes=31)
        AssetTranscriptionReservation.objects.update(
            created_on=old_timestamp, updated_on=old_timestamp
        )

        expire_inactive_asset_reservations()

        self.login_user()

        # 1 reservation check + 1 acquire + 1 get user ID from request
        expected_queries = 3
        if settings.SESSION_ENGINE.endswith("db"):
            # 1 session check
            expected_queries += 1

        with self.assertNumQueries(expected_queries):
            resp = self.client.post(reverse("reserve-asset", args=(asset.pk,)))

        data = self.assertValidJSON(resp, expected_status=200)
        self.assertEqual(1, AssetTranscriptionReservation.objects.count())
        reservation = AssetTranscriptionReservation.objects.get()
        self.assertEqual(reservation.reservation_token, data["reservation_token"])

    def test_asset_reservation_tombstone(self):
        """
        Simulate a tombstoned reservation which should:
            - return 408 during the tombstone period
            - during the tombstone period, another user may
              obtain the reservation but the original user may not
        """
        asset = create_asset()
        self.login_user()
        request_factory = RequestFactory()
        request = request_factory.get("/")
        request.session = {}
        reservation_token = get_or_create_reservation_token(request)

        session = self.client.session
        session["reservation_token"] = reservation_token
        session.save()

        tombstone_reservation = AssetTranscriptionReservation(  # nosec
            asset=asset, reservation_token=reservation_token
        )
        tombstone_reservation.full_clean()
        tombstone_reservation.save()
        # Backdate the object as if it was created hours ago,
        # even if it was recently updated
        old_timestamp = now() - timedelta(
            hours=settings.TRANSCRIPTION_RESERVATION_TOMBSTONE_HOURS + 1
        )
        current_timestamp = now()
        AssetTranscriptionReservation.objects.update(
            created_on=old_timestamp, updated_on=current_timestamp
        )

        tombstone_old_active_asset_reservations()
        self.assertEqual(1, AssetTranscriptionReservation.objects.count())
        reservation = AssetTranscriptionReservation.objects.get()
        self.assertEqual(reservation.tombstoned, True)

        # 1 session check + 1 reservation check
        if settings.SESSION_ENGINE.endswith("db"):
            expected_queries = 2
        else:
            expected_queries = 1

        with self.assertNumQueries(expected_queries):
            resp = self.client.post(reverse("reserve-asset", args=(asset.pk,)))

        self.assertEqual(resp.status_code, 408)
        self.assertEqual(1, AssetTranscriptionReservation.objects.count())
        reservation = AssetTranscriptionReservation.objects.get()
        self.assertEqual(reservation.reservation_token, reservation_token)

        self.client.logout()

        # 1 reservation check + 1 acquire + 2 get user ID
        # + 2 get user profile from request
        expected_queries = 6
        if settings.SESSION_ENGINE.endswith("db"):
            # + 1 session check
            expected_queries += 1

        with self.assertNumQueries(expected_queries):
            resp = self.client.post(reverse("reserve-asset", args=(asset.pk,)))

        self.assertValidJSON(resp, expected_status=200)
        self.assertEqual(2, AssetTranscriptionReservation.objects.count())

    def test_asset_reservation_tombstone_expiration(self):
        """
        Simulate a tombstoned reservation which should expire after
        the configured period of time, allowing the original user
        to reserve the asset again
        """
        asset = create_asset()
        self.login_user()
        request_factory = RequestFactory()
        request = request_factory.get("/")
        request.session = {}
        reservation_token = get_or_create_reservation_token(request)

        session = self.client.session
        session["reservation_token"] = reservation_token
        session.save()

        tombstone_reservation = AssetTranscriptionReservation(  # nosec
            asset=asset, reservation_token=reservation_token
        )
        tombstone_reservation.full_clean()
        tombstone_reservation.save()
        # Backdate the object as if it was created hours ago
        # and tombstoned hours ago
        old_timestamp = now() - timedelta(
            hours=settings.TRANSCRIPTION_RESERVATION_TOMBSTONE_HOURS
            + settings.TRANSCRIPTION_RESERVATION_TOMBSTONE_LENGTH_HOURS
            + 1
        )
        not_as_old_timestamp = now() - timedelta(
            hours=settings.TRANSCRIPTION_RESERVATION_TOMBSTONE_LENGTH_HOURS + 1
        )
        AssetTranscriptionReservation.objects.update(
            created_on=old_timestamp, updated_on=not_as_old_timestamp, tombstoned=True
        )

        delete_old_tombstoned_reservations()
        self.assertEqual(0, AssetTranscriptionReservation.objects.count())

        # 1 session check + 1 reservation check + 1 acquire
        if settings.SESSION_ENGINE.endswith("db"):
            expected_queries = 3
        else:
            expected_queries = 2

        with self.assertNumQueries(expected_queries):
            resp = self.client.post(reverse("reserve-asset", args=(asset.pk,)))

        data = self.assertValidJSON(resp, expected_status=200)
        self.assertEqual(1, AssetTranscriptionReservation.objects.count())
        reservation = AssetTranscriptionReservation.objects.get()
        self.assertEqual(reservation.reservation_token, data["reservation_token"])
        self.assertEqual(reservation.tombstoned, False)

    def test_transcription_save(self):
        asset = create_asset()

        with patch("concordia.turnstile.fields.TurnstileField.validate") as mock:
            mock.side_effect = forms.ValidationError(
                "Testing error", code="invalid_turnstile"
            )
            resp = self.client.post(
                reverse("save-transcription", args=(asset.pk,)), data={"text": "test"}
            )
            data = self.assertValidJSON(resp, expected_status=401)
            self.assertIn("error", data)

        with patch(
            "concordia.turnstile.fields.TurnstileField.validate", return_value=True
        ):
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

        with patch("concordia.turnstile.fields.TurnstileField.validate") as mock:
            mock.side_effect = forms.ValidationError(
                "Testing error", code="invalid_turnstile"
            )
            resp = self.client.post(
                reverse("submit-transcription", args=(transcription.pk,))
            )
        data = self.assertValidJSON(resp, expected_status=401)
        self.assertIn("error", data)

        self.assertFalse(Transcription.objects.filter(submitted__isnull=False).exists())

        with patch(
            "concordia.turnstile.fields.TurnstileField.validate", return_value=True
        ):
            self.client.post(
                reverse("submit-transcription", args=(transcription.pk,)),
            )
            self.assertTrue(
                Transcription.objects.filter(submitted__isnull=False).exists()
            )

    def test_transcription_submission(self):
        asset = create_asset()

        with patch(
            "concordia.turnstile.fields.TurnstileField.validate", return_value=True
        ):
            resp = self.client.post(
                reverse("save-transcription", args=(asset.pk,)), data={"text": "test"}
            )
        data = self.assertValidJSON(resp, expected_status=201)

        transcription = Transcription.objects.get()
        self.assertIsNone(transcription.submitted)

        with patch(
            "concordia.turnstile.fields.TurnstileField.validate", return_value=True
        ):
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

        anon = get_anonymous_user()

        t1 = Transcription(asset=asset, user=anon, text="test")
        t1.full_clean()
        t1.save()

        t2 = Transcription(asset=asset, user=anon, text="test", supersedes=t1)
        t2.full_clean()
        t2.save()

        with patch(
            "concordia.turnstile.fields.TurnstileField.validate", return_value=True
        ):
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

    def test_tag_submission_with_diacritics(self):
        asset = create_asset()

        self.login_user()

        test_tags = ["Café", "château", "señor", "façade"]

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

        second_user = self.create_test_user(
            username="second_tester", email="second_tester@example.com"
        )
        self.client.login(username=second_user.username, password=second_user._password)

        resp = self.client.post(
            reverse("submit-tags", kwargs={"asset_pk": asset.pk}),
            data={"tags": ["foo", "bar", "quux"]},
        )
        data = self.assertValidJSON(resp, expected_status=200)

        # Even though the user submitted (through some horrible bug) duplicate
        # values, they should not be stored:
        self.assertEqual(["bar", "foo", "quux"], data["user_tags"])
        # Users are allowed to delete other users' tags, so since the second
        # user didn't send the "baaz" tag, it was removed
        self.assertEqual(["bar", "foo", "quux"], data["all_tags"])

    def test_tag_deletion(self):
        asset = create_asset()
        self.login_user()

        initial_tags = ["foo", "bar"]
        self.client.post(
            reverse("submit-tags", kwargs={"asset_pk": asset.pk}),
            data={"tags": initial_tags},
        )
        updated_tags = [
            "foo",
        ]
        resp = self.client.post(
            reverse("submit-tags", kwargs={"asset_pk": asset.pk}),
            data={"tags": updated_tags},
        )
        data = self.assertValidJSON(resp, expected_status=200)
        self.assertIn("user_tags", data)
        self.assertIn("all_tags", data)

        self.assertCountEqual(updated_tags, data["user_tags"])
        self.assertCountEqual(updated_tags, data["all_tags"])

    def test_tag_deletion_with_multiple_users(self):
        asset = create_asset()
        self.login_user("first_user")
        initial_tags = ["foo", "bar"]
        resp = self.client.post(
            reverse("submit-tags", kwargs={"asset_pk": asset.pk}),
            data={"tags": initial_tags},
        )
        self.assertIn(
            "first_user",
            asset.userassettagcollection_set.values().values_list(
                "user__username", flat=True
            ),
        )
        data = self.assertValidJSON(resp, expected_status=200)
        self.assertIn("user_tags", data)
        self.assertIn("all_tags", data)
        self.assertCountEqual(initial_tags, data["user_tags"])
        self.assertCountEqual(initial_tags, data["all_tags"])

        self.client.logout()

        second_user = self.create_test_user("second_user")
        self.client.login(username=second_user.username, password=second_user._password)
        updated_tags = [
            "foo",
        ]
        resp = self.client.post(
            reverse("submit-tags", kwargs={"asset_pk": asset.pk}),
            data={"tags": updated_tags},
        )
        data = self.assertValidJSON(resp, expected_status=200)

        self.assertIn(
            "second_user",
            asset.userassettagcollection_set.values().values_list(
                "user__username", flat=True
            ),
        )
        self.assertEqual(asset.userassettagcollection_set.count(), 2)
        self.assertEqual(
            User.objects.filter(userassettagcollection__asset=asset).count(), 2
        )
        self.assertIn("user_tags", data)
        self.assertIn("all_tags", data)
        self.assertCountEqual(updated_tags, data["user_tags"])

    def test_find_next_transcribable_no_campaign(self):
        asset1 = create_asset(slug="test-asset-1")
        create_asset(item=asset1.item, slug="test-asset-2")
        resp = self.client.get(reverse("redirect-to-next-transcribable-asset"))

        self.assertRedirects(resp, expected_url=asset1.get_absolute_url())

    def test_find_next_reviewable_no_campaign(self):
        user = self.create_user("test-user")
        anon = get_anonymous_user()

        asset1 = create_asset(slug="test-asset-1")
        asset2 = create_asset(item=asset1.item, slug="test-asset-2")

        t1 = Transcription(asset=asset1, user=user, text="test", submitted=now())
        t1.full_clean()
        t1.save()

        t2 = Transcription(asset=asset2, user=anon, text="test", submitted=now())
        t2.full_clean()
        t2.save()

        response = self.client.get(reverse("redirect-to-next-reviewable-asset"))

        self.assertRedirects(response, expected_url=asset1.get_absolute_url())

    def test_find_next_transcribable_campaign(self):
        asset1 = create_asset(slug="test-asset-1")
        create_asset(item=asset1.item, slug="test-asset-2")
        campaign = asset1.item.project.campaign

        resp = self.client.get(
            reverse(
                "transcriptions:redirect-to-next-transcribable-campaign-asset",
                kwargs={"campaign_slug": campaign.slug},
            )
        )

        self.assertRedirects(resp, expected_url=asset1.get_absolute_url())

    def test_find_next_transcribable_topic(self):
        asset1 = create_asset(slug="test-asset-1")
        create_asset(item=asset1.item, slug="test-asset-2")
        project = asset1.item.project
        topic = create_topic(project=project)

        resp = self.client.get(
            reverse(
                "redirect-to-next-transcribable-topic-asset",
                kwargs={"topic_slug": topic.slug},
            )
        )

        self.assertRedirects(resp, expected_url=asset1.get_absolute_url())

    def test_find_next_reviewable_campaign(self):
        anon = get_anonymous_user()

        asset1 = create_asset(slug="test-review-asset-1")
        asset2 = create_asset(item=asset1.item, slug="test-review-asset-2")

        t1 = Transcription(asset=asset1, user=anon, text="test", submitted=now())
        t1.full_clean()
        t1.save()

        t2 = Transcription(asset=asset2, user=anon, text="test", submitted=now())
        t2.full_clean()
        t2.save()

        campaign = asset1.item.project.campaign

        response = self.client.get(
            reverse(
                "transcriptions:redirect-to-next-reviewable-campaign-asset",
                kwargs={"campaign_slug": campaign.slug},
            )
        )

        self.assertRedirects(response, expected_url=asset1.get_absolute_url())

    def test_find_next_reviewable_topic(self):
        anon = get_anonymous_user()

        asset1 = create_asset(slug="test-review-asset-1")
        asset2 = create_asset(item=asset1.item, slug="test-review-asset-2")
        project = asset1.item.project
        topic = create_topic(project=project)

        t1 = Transcription(asset=asset1, user=anon, text="test", submitted=now())
        t1.full_clean()
        t1.save()

        t2 = Transcription(asset=asset2, user=anon, text="test", submitted=now())
        t2.full_clean()
        t2.save()

        response = self.client.get(
            reverse(
                "redirect-to-next-reviewable-topic-asset",
                kwargs={"topic_slug": topic.slug},
            )
        )

        self.assertRedirects(response, expected_url=asset1.get_absolute_url())

    def test_find_next_reviewable_unlisted_campaign(self):
        anon = get_anonymous_user()

        unlisted_campaign = create_campaign(
            slug="campaign-transcribe-redirect-unlisted",
            title="Test Unlisted Review Redirect Campaign",
            unlisted=True,
        )
        unlisted_project = create_project(
            title="Unlisted Project",
            slug="unlisted-project",
            campaign=unlisted_campaign,
        )
        unlisted_item = create_item(
            title="Unlisted Item",
            item_id="unlisted-item",
            item_url="https://blah.com/unlisted-item",
            project=unlisted_project,
        )

        asset1 = create_asset(slug="test-asset-1", item=unlisted_item)
        asset2 = create_asset(item=asset1.item, slug="test-asset-2")

        t1 = Transcription(asset=asset1, user=anon, text="test", submitted=now())
        t1.full_clean()
        t1.save()

        t2 = Transcription(asset=asset2, user=anon, text="test", submitted=now())
        t2.full_clean()
        t2.save()

        response = self.client.get(
            reverse(
                "transcriptions:redirect-to-next-reviewable-campaign-asset",
                kwargs={"campaign_slug": unlisted_campaign.slug},
            )
        )

        self.assertRedirects(response, expected_url=asset1.get_absolute_url())

    def test_find_next_transcribable_unlisted_campaign(self):
        unlisted_campaign = create_campaign(
            slug="campaign-transcribe-redirect-unlisted",
            title="Test Unlisted Transcribe Redirect Campaign",
            unlisted=True,
        )
        unlisted_project = create_project(
            title="Unlisted Project",
            slug="unlisted-project",
            campaign=unlisted_campaign,
        )
        unlisted_item = create_item(
            title="Unlisted Item",
            item_id="unlisted-item",
            item_url="https://blah.com/unlisted-item",
            project=unlisted_project,
        )

        asset1 = create_asset(slug="test-asset-1", item=unlisted_item)
        create_asset(item=asset1.item, slug="test-asset-2")

        response = self.client.get(
            reverse(
                "transcriptions:redirect-to-next-transcribable-campaign-asset",
                kwargs={"campaign_slug": unlisted_campaign.slug},
            )
        )

        self.assertRedirects(response, expected_url=asset1.get_absolute_url())

    def test_find_next_transcribable_single_asset(self):
        asset = create_asset()
        campaign = asset.item.project.campaign

        resp = self.client.get(
            reverse(
                "transcriptions:redirect-to-next-transcribable-campaign-asset",
                kwargs={"campaign_slug": campaign.slug},
            )
        )

        self.assertRedirects(resp, expected_url=asset.get_absolute_url())

    def test_find_next_transcribable_in_singleton_campaign(self):
        asset = create_asset(transcription_status=TranscriptionStatus.SUBMITTED)
        campaign = asset.item.project.campaign

        resp = self.client.get(
            reverse(
                "transcriptions:redirect-to-next-transcribable-campaign-asset",
                kwargs={"campaign_slug": campaign.slug},
            )
        )

        self.assertRedirects(resp, expected_url=reverse("homepage"))

    def test_find_next_transcribable_project_redirect(self):
        asset = create_asset(transcription_status=TranscriptionStatus.SUBMITTED)
        project = asset.item.project
        campaign = project.campaign

        resp = self.client.get(
            "%s?project=%s"
            % (
                reverse(
                    "transcriptions:redirect-to-next-transcribable-campaign-asset",
                    kwargs={"campaign_slug": campaign.slug},
                ),
                project.slug,
            )
        )

        self.assertRedirects(resp, expected_url=reverse("homepage"))

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
                    "transcriptions:redirect-to-next-transcribable-campaign-asset",
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
                    "transcriptions:redirect-to-next-transcribable-campaign-asset",
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
                    "transcriptions:redirect-to-next-transcribable-campaign-asset",
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
                    "transcriptions:redirect-to-next-transcribable-campaign-asset",
                    kwargs={"campaign_slug": campaign.slug},
                ),
                {"project": project.slug, "item": item.item_id, "asset": asset.pk},
            ),
            in_progress_asset_in_item.get_absolute_url(),
        )


class FilteredCampaignDetailViewTests(CreateTestUsers, TestCase):
    def test_get_context_data(self):
        campaign = create_campaign()
        kwargs = {"slug": campaign.slug}
        url = reverse("transcriptions:filtered-campaign-detail", kwargs=kwargs)

        self.login_user(is_staff=False)
        response = self.client.get(url, kwargs)
        self.assertFalse(response.context.get("filter_by_reviewable", False))
        self.logout_user()

        self.user = self.create_staff_user()
        self.login_user()
        response = self.client.get(url, kwargs)
        self.assertTrue(response.context.get("filter_by_reviewable"))


class FilteredProjectDetailViewTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.project = create_project()
        self.kwargs = {
            "campaign_slug": self.project.campaign.slug,
            "slug": self.project.slug,
        }
        self.url = reverse("transcriptions:filtered-project-detail", kwargs=self.kwargs)
        self.login_user()

    def test_get_queryset(self):
        item1 = create_item(project=self.project, item_id="testitem.012345679")
        asset1 = create_asset(item=item1)
        create_transcription(asset=asset1, user=get_anonymous_user(), submitted=now())

        item2 = create_item(
            project=create_project(slug="project-two", campaign=self.project.campaign)
        )
        asset2 = create_asset(item=item2)
        create_transcription(asset=asset2, user=self.user, submitted=now())

        view = FilteredProjectDetailView()
        view.kwargs = self.kwargs
        view.request = RequestFactory().get(self.url, self.kwargs)
        view.request.user = self.user
        qs = view.get_queryset()
        self.assertIn(item1, qs)
        self.assertNotIn(item2, qs)

    def test_get_context_data(self):
        response = self.client.get(self.url, self.kwargs)
        self.assertTrue(response.context.get("filter_by_reviewable"))


class FilteredItemDetailViewTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.item = create_item()
        self.kwargs = {
            "campaign_slug": self.item.project.campaign.slug,
            "project_slug": self.item.project.slug,
            "item_id": self.item.item_id,
        }
        self.url = reverse("transcriptions:filtered-item-detail", kwargs=self.kwargs)
        self.login_user()

    def test_get_queryset(self):
        asset1 = create_asset(item=self.item)
        create_transcription(asset=asset1, user=get_anonymous_user(), submitted=now())

        asset2 = create_asset(item=self.item, slug="asset-two")
        create_transcription(asset=asset2, user=self.user, submitted=now())

        view = FilteredItemDetailView()
        view.kwargs = self.kwargs
        view.request = RequestFactory().get(self.url, self.kwargs)
        view.request.user = self.user
        qs = view.get_queryset()
        self.assertIn(asset1, qs)
        self.assertNotIn(asset2, qs)

    def test_get_context_data(self):
        response = self.client.get(self.url, self.kwargs)
        self.assertTrue(response.context.get("filter_by_reviewable"))


class RateLimitTests(TestCase):
    def setUp(self):
        self.request_factory = RequestFactory()

    def test_registration_rate(self):
        request = self.request_factory.get("/")
        self.assertEqual(registration_rate(None, request), "10/h")
        with patch("concordia.views.UserRegistrationForm", autospec=True):
            # This causes the form to test as valid even though there's no data
            self.assertIsNone(registration_rate(None, request))

    def test_ratelimit_view(self):
        request = self.request_factory.post("/")
        exception = Exception()
        response = ratelimit_view(request, exception)
        self.assertEqual(response.status_code, 429)
        self.assertNotEqual(response["Retry-After"], 0)


class LoginTests(TestCase, CreateTestUsers):
    def setUp(self):
        self.user = self.create_user("test-user")

    def test_ConcordiaLoginView(self):
        with patch("concordia.turnstile.fields.TurnstileField.validate") as mock:
            mock.side_effect = forms.ValidationError(
                "Testing error", code="invalid_turnstile"
            )
            response = self.client.post(
                reverse("registration_login"),
                data={"username": self.user.username, "password": self.user._password},
            )
        self.assertIn("user", response.context)
        self.assertFalse(response.context["user"].is_authenticated)

        with patch(
            "concordia.turnstile.fields.TurnstileField.validate", return_value=True
        ):
            response = self.client.post(
                reverse("registration_login"),
                data={"username": self.user.username, "password": self.user._password},
                follow=True,
            )
        self.assertRedirects(
            response,
            expected_url=reverse("homepage"),
            target_status_code=200,
        )
        self.assertIn("user", response.context)
        self.assertTrue(response.context["user"].is_authenticated)
