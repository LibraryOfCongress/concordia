import json
from datetime import date, timedelta
from unittest.mock import patch

from django import forms
from django.contrib.auth.models import AnonymousUser
from django.core.cache import caches
from django.db.models.signals import post_save
from django.http import HttpResponse, JsonResponse
from django.test import (
    Client,
    RequestFactory,
    TestCase,
    override_settings,
)
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.timezone import now

from concordia.models import (
    Asset,
    Campaign,
    Transcription,
)
from concordia.signals.handlers import on_transcription_save
from concordia.tasks.reports.sitereport import campaign_report
from concordia.utils import get_anonymous_user
from concordia.views.accounts import AccountProfileView, registration_rate
from concordia.views.campaigns import CompletedCampaignListView
from concordia.views.decorators import reserve_rate, user_cache_control
from concordia.views.items import FilteredItemDetailView
from concordia.views.projects import FilteredProjectDetailView
from concordia.views.rate_limit import ratelimit_view
from concordia.views.visualizations import VisualizationDataView

from .utils import (
    CreateTestUsers,
    JSONAssertMixin,
    create_asset,
    create_campaign,
    create_card_family,
    create_guide,
    create_item,
    create_project,
    create_research_center,
    create_tag_collection,
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
        yesterday = today - timedelta(days=1)

        self.research_center = create_research_center()
        self.campaign2 = create_campaign(
            published=True,
            status=Campaign.Status.COMPLETED,
            slug="test-campaign-2",
            completed_date=yesterday,
        )
        self.campaign2.research_centers.add(self.research_center)
        self.campaign3 = create_campaign(
            published=True,
            status=Campaign.Status.RETIRED,
            slug="test-campaign-3",
            completed_date=yesterday,
        )

    def test_get_all_campaigns(self):
        active = create_campaign(
            published=True,
            slug="test-campaign-4",
            completed_date=self.campaign2.completed_date,
        )
        view = CompletedCampaignListView()
        view.request = RequestFactory().get("/campaigns/completed/")
        completed_and_retired = view._get_all_campaigns()
        self.assertNotIn(active, completed_and_retired)
        self.assertIn(self.campaign2, completed_and_retired)
        self.assertIn(self.campaign3, completed_and_retired)

        view.request = RequestFactory().get("/campaigns/completed/?type=completed")
        completed_campaigns = view._get_all_campaigns()
        self.assertNotIn(active, completed_campaigns)
        self.assertIn(self.campaign2, completed_campaigns)
        self.assertNotIn(self.campaign3, completed_campaigns)

        view.request = RequestFactory().get("/campaigns/completed/?type=retired")
        retired_campaigns = view._get_all_campaigns()
        self.assertNotIn(active, retired_campaigns)
        self.assertNotIn(self.campaign2, retired_campaigns)
        self.assertIn(self.campaign3, retired_campaigns)

    def test_queryset(self):
        today = date.today()
        create_campaign(
            published=True, status=Campaign.Status.COMPLETED, completed_date=today
        )

        view = CompletedCampaignListView()

        # Test default
        view.request = RequestFactory().get("/campaigns/completed/")
        queryset = view.get_queryset()
        self.assertGreater(
            queryset.first().completed_date, queryset.last().completed_date
        )

        # Test retired
        view.request = RequestFactory().get("/campaigns/completed/?type=retired")
        queryset = view.get_queryset()
        self.assertEqual(queryset.count(), 1)

    def test_context_data(self):
        request = RequestFactory().get("/campaigns/completed/")
        response = CompletedCampaignListView.as_view()(request)
        self.assertIsInstance(response.context_data, dict)
        self.assertEqual(response.context_data["result_count"], 2)

        request = RequestFactory().get("/campaigns/completed/?type=completed")
        response = CompletedCampaignListView.as_view()(request)
        self.assertIsInstance(response.context_data, dict)
        self.assertEqual(response.context_data["result_count"], 1)

        request = RequestFactory().get("/campaigns/completed/?type=completed")
        response = CompletedCampaignListView.as_view()(request)
        self.assertIsInstance(response.context_data, dict)
        self.assertEqual(response.context_data["result_count"], 1)

        request = RequestFactory().get(
            f"/campaigns/completed/?research_center={self.research_center.id}"
        )
        response = CompletedCampaignListView.as_view()(request)
        self.assertIsInstance(response.context_data, dict)
        self.assertEqual(response.context_data["result_count"], 1)

    def test_research_centers(self):
        today = date.today()

        create_campaign(
            published=True, status=Campaign.Status.COMPLETED, completed_date=today
        )

        url = f"/campaigns/completed/?research_center={self.research_center.id}"

        # Test queryset directly
        view = CompletedCampaignListView()
        view.request = RequestFactory().get(url)
        queryset = view.get_queryset()

        self.assertEqual(queryset.count(), 1)

        # Test get_context_data through a get
        response = self.client.get(url)

        self.assertIn("research_centers", response.context)
        self.assertEqual(response.context["research_centers"][0], self.research_center)


@override_settings(
    RATELIMIT_ENABLE=False, SESSION_ENGINE="django.contrib.sessions.backends.cache"
)
class ConcordiaViewTests(CreateTestUsers, JSONAssertMixin, TestCase):
    """
    This class contains the unit tests for the view in the concordia app.
    """

    def setUp(self):
        for cache in caches.all():
            cache.clear()

    def tearDown(self):
        for cache in caches.all():
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

    def test_campaign_detail_view(self):
        """
        Test GET on route /campaigns/<slug-value> (campaign)
        """
        campaign = create_campaign(title="GET Campaign", slug="get-campaign")
        response = self.client.get(
            reverse("transcriptions:campaign-detail", args=(campaign.slug,))
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/campaign_detail.html"
        )
        self.assertContains(response, campaign.title)
        # Filter by reviewable parameter check
        response = self.client.get(
            reverse("transcriptions:campaign-detail", args=(campaign.slug,)),
            {"filter_by_reviewable": True},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/campaign_detail.html"
        )
        self.assertContains(response, campaign.title)
        # Bad status parameter check
        response = self.client.get(
            reverse("transcriptions:campaign-detail", args=(campaign.slug,)),
            {"transcription_status": "bad_parameter"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/campaign_detail.html"
        )
        self.assertContains(response, campaign.title)

        # Unlisted
        campaign = create_campaign(
            title="GET Unlisted Campaign", unlisted=True, slug="get-unlisted-campaign"
        )
        response = self.client.get(
            reverse("transcriptions:campaign-detail", args=(campaign.slug,))
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/campaign_detail.html"
        )
        self.assertContains(response, campaign.title)

        # Completed
        campaign = create_campaign(
            title="GET Completed Campaign",
            slug="get-completed-campaign",
            status=Campaign.Status.COMPLETED,
        )
        response = self.client.get(
            reverse("transcriptions:campaign-detail", args=(campaign.slug,))
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/campaign_detail_completed.html"
        )
        self.assertContains(response, campaign.title)

        # Retired
        campaign = create_campaign(
            title="GET Retired Campaign",
            slug="get-retired-campaign",
            status=Campaign.Status.RETIRED,
        )
        # We need a site report for a retired campaign because
        # that's where the view pulls data from
        campaign_report(campaign=campaign)
        response = self.client.get(
            reverse("transcriptions:campaign-detail", args=(campaign.slug,))
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/campaign_detail_retired.html"
        )
        self.assertContains(response, campaign.title)

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
        # Filter by reviewable parameter check
        response = self.client.get(
            reverse(
                "transcriptions:item-detail",
                args=(item.project.campaign.slug, item.project.slug, item.item_id),
            ),
            {"filter_by_reviewable": True},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/item_detail.html"
        )
        # Bad status parameter check
        response = self.client.get(
            reverse(
                "transcriptions:item-detail",
                args=(item.project.campaign.slug, item.project.slug, item.item_id),
            ),
            {"transcription_status": "bad_parameter"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/item_detail.html"
        )

        # Non-existent item in an existing campaign
        response = self.client.get(
            reverse(
                "transcriptions:item-detail",
                args=(item.project.campaign.slug, item.project.slug, "bad-id"),
            )
        )
        self.assertRedirects(
            response,
            reverse(
                "transcriptions:campaign-detail", args=(item.project.campaign.slug,)
            ),
        )

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

        asset = create_asset(sequence=100)

        self.transcription = asset.transcription_set.create(
            user_id=self.user.id, text="Test transcription 1"
        )
        self.transcription.save()

        asset.item.project.campaign.card_family = create_card_family()
        asset.item.project.campaign.save()
        title = "Transcription: Basic Rules"
        create_guide(title=title)

        tag_collection = create_tag_collection(asset=asset)

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
        self.assertIn("tags", response.context)
        self.assertEqual([tag_collection.tags.all()[0].value], response.context["tags"])

        # Next and previous asset checks
        previous_asset = create_asset(
            item=asset.item, slug="previous-asset", sequence=1
        )
        next_asset = create_asset(item=asset.item, slug="next-asset", sequence=1000)
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
        self.assertIn("previous_asset_url", response.context)
        self.assertEqual(
            previous_asset.get_absolute_url(), response.context["previous_asset_url"]
        )
        self.assertIn("next_asset_url", response.context)
        self.assertEqual(
            next_asset.get_absolute_url(), response.context["next_asset_url"]
        )

        # Download URL iiif check
        asset.download_url = "http://tile.loc.gov/image-services/iiif/service:music:mussuffrage:mussuffrage-100183:mussuffrage-100183.0001/full/pct:100/0/default.jpg"
        asset.save()
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
        self.assertIn("thumbnail_url", response.context)
        self.assertEqual(
            "https://tile.loc.gov/image-services/iiif/service:music:mussuffrage:mussuffrage-100183:mussuffrage-100183.0001/full/!512,512/0/default.jpg",
            response.context["thumbnail_url"],
        )

        # Non-existent asset in an existing campaign
        response = self.client.get(
            reverse(
                "transcriptions:asset-detail",
                kwargs={
                    "campaign_slug": asset.item.project.campaign.slug,
                    "project_slug": asset.item.project.slug,
                    "item_id": asset.item.item_id,
                    "slug": "bad-slug",
                },
            )
        )
        self.assertRedirects(
            response,
            reverse(
                "transcriptions:campaign-detail",
                args=(asset.item.project.campaign.slug,),
            ),
        )

    @patch.object(Asset, "get_ocr_transcript")
    def test_generate_ocr_transcription(self, mock):
        asset1 = create_asset(storage_image="tests/test-european.jpg")
        url = reverse("generate-ocr-transcription", kwargs={"asset_pk": asset1.pk})

        # Anonymous user test; should redirect
        response = self.client.post(url)
        self.assertEqual(302, response.status_code)
        self.assertFalse(mock.called)
        mock.reset_mock()

        self.login_user()
        response = self.client.post(url)
        self.assertEqual(201, response.status_code)
        self.assertTrue(mock.called)
        mock.reset_mock()

        asset2 = create_asset(
            item=asset1.item,
            slug="test-asset-2",
            storage_image="tests/test-european.jpg",
        )
        url = reverse("generate-ocr-transcription", kwargs={"asset_pk": asset2.pk})
        response = self.client.post(url, data={"language": "spa"})
        self.assertEqual(201, response.status_code)
        mock.assert_called_with("spa")
        mock.reset_mock()

        with patch(
            "concordia.views.ajax.get_transcription_superseded"
        ) as superseded_mock:
            # Test case if the trancription being replaced has already been superseded
            superseded_mock.return_value = HttpResponse(status=409)
            url = reverse("generate-ocr-transcription", kwargs={"asset_pk": asset2.pk})
            response = self.client.post(url)
            self.assertEqual(409, response.status_code)
            self.assertTrue(superseded_mock.called)
            self.assertFalse(mock.called)

            # Test case if the transcription being replaced hasn't been superseded
            superseded_mock.reset_mock()
            superseded_mock.return_value = create_transcription(
                asset=asset2, user=get_anonymous_user(), submitted=now()
            )
            url = reverse("generate-ocr-transcription", kwargs={"asset_pk": asset2.pk})
            response = self.client.post(url)
            self.assertEqual(201, response.status_code)
            self.assertTrue(superseded_mock.called)
            self.assertTrue(mock.called)

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
        # Filter by reviewable parameter check
        response = self.client.get(
            reverse(
                "transcriptions:project-detail",
                args=(project.campaign.slug, project.slug),
            ),
            {"filter_by_reviewable": True},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/project_detail.html"
        )
        # Bad status parameter check
        response = self.client.get(
            reverse(
                "transcriptions:project-detail",
                args=(project.campaign.slug, project.slug),
            ),
            {"transcription_status": "bad_parameter"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/project_detail.html"
        )

        # Non-existent project in an existing campaign
        response = self.client.get(
            reverse(
                "transcriptions:project-detail",
                args=(project.campaign.slug, "bad-slug"),
            )
        )
        self.assertRedirects(
            response,
            reverse("transcriptions:campaign-detail", args=(project.campaign.slug,)),
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


class UserCacheControlTest(CreateTestUsers, TestCase):
    """
    Tests for the user_cache_control decorator
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.user = self.create_user("testuser")

    def test_vary_on_cookie(self):
        @method_decorator(user_cache_control, name="dispatch")
        def a_view(request):
            return HttpResponse()

        request = self.factory.get("/rand")
        request.user = self.user
        resp = a_view(None, request)
        self.assertEqual(resp.status_code, 200)


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

    def tearDown(self):
        post_save.connect(on_transcription_save, sender=Transcription)


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

    def tearDown(self):
        post_save.connect(on_transcription_save, sender=Transcription)


class RateLimitTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.request_factory = RequestFactory()
        self.user = self.create_user("test-user")

    def test_registration_rate(self):
        request = self.request_factory.get("/")
        self.assertEqual(registration_rate(None, request), "10/h")
        with patch("concordia.views.accounts.UserRegistrationForm", autospec=True):
            # This causes the form to test as valid even though there's no data
            self.assertIsNone(registration_rate(None, request))

    def test_ratelimit_view(self):
        request = self.request_factory.post("/")
        exception = Exception()
        response = ratelimit_view(request, exception)
        self.assertEqual(response.status_code, 429)
        self.assertNotEqual(response["Retry-After"], 0)

    def test_reserve_rate(self):
        request = self.request_factory.post("/")

        request.user = AnonymousUser()
        self.assertEqual("100/m", reserve_rate("test.group", request))

        request.user = self.user
        self.assertEqual(None, reserve_rate("test.group", request))


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


class TranscriptionViewTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.asset = create_asset()

    def test_rollback_transcription(self):
        path = reverse("rollback-transcription", args=[self.asset.id])
        self.login_user()

        # Test rollback when there are no transcriptions
        response = self.client.post(path)
        self.assertEqual(400, response.status_code)
        self.assertIn("error", response.json())

        transcription1 = create_transcription(
            asset=self.asset, text="Test transcription 1"
        )
        user = transcription1.user

        # Test rollback when there are no transcriptions to rollback to
        response = self.client.post(path)
        self.assertEqual(400, response.status_code)
        self.assertIn("error", response.json())

        # Test successful rollback
        create_transcription(asset=self.asset, user=user, text="Test transcription 2")
        response = self.client.post(path)
        self.assertEqual(201, response.status_code)
        response_json = response.json()
        self.assertIn("id", response_json)
        self.assertIn("text", response_json)
        self.assertEqual(response_json["text"], transcription1.text)
        self.assertIn("undo_available", response_json)
        self.assertEqual(response_json["undo_available"], False)
        self.assertIn("redo_available", response_json)
        self.assertEqual(response_json["redo_available"], True)

        # Test after a rollforward
        self.asset.rollforward_transcription(user)
        response = self.client.post(path)
        self.assertEqual(201, response.status_code)
        response_json = response.json()
        self.assertIn("id", response_json)
        self.assertIn("text", response_json)
        self.assertEqual(response_json["text"], transcription1.text)
        self.assertIn("undo_available", response_json)
        self.assertEqual(response_json["undo_available"], False)
        self.assertIn("redo_available", response_json)
        self.assertEqual(response_json["redo_available"], True)

        # Test anonymous user
        self.client.logout()
        create_transcription(asset=self.asset, user=user, text="Test transcription 3")
        with patch(
            "concordia.turnstile.fields.TurnstileField.validate", return_value=True
        ):
            response = self.client.post(path)
        self.assertEqual(201, response.status_code)
        response_json = response.json()
        self.assertIn("id", response_json)
        self.assertIn("text", response_json)
        self.assertEqual(response_json["text"], transcription1.text)
        self.assertIn("undo_available", response_json)
        self.assertEqual(response_json["undo_available"], False)
        self.assertIn("redo_available", response_json)
        self.assertEqual(response_json["redo_available"], True)

    def test_rollforward_transcription(self):
        path = reverse("rollforward-transcription", args=[self.asset.id])
        self.login_user()

        # Test rollforward when there are no transcriptions
        response = self.client.post(path)
        self.assertEqual(400, response.status_code)
        self.assertIn("error", response.json())

        transcription1 = create_transcription(
            asset=self.asset, text="Test transcription 1"
        )
        user = transcription1.user

        # Test rollback when there are no transcriptions to rollforward to
        response = self.client.post(path)
        self.assertEqual(400, response.status_code)
        self.assertIn("error", response.json())

        # Test successful rollforward, which requires a rollback first
        transcription2 = create_transcription(
            asset=self.asset, user=user, text="Test transcription 2"
        )
        self.asset.rollback_transcription(user)
        response = self.client.post(path)
        self.assertEqual(201, response.status_code)
        response_json = response.json()
        self.assertIn("id", response_json)
        self.assertIn("text", response_json)
        self.assertEqual(response_json["text"], transcription2.text)
        self.assertIn("undo_available", response_json)
        self.assertEqual(response_json["undo_available"], True)
        self.assertIn("redo_available", response_json)
        self.assertEqual(response_json["redo_available"], False)

        # Test aftering rolling back then creating a new transcription
        self.asset.rollback_transcription(user)
        create_transcription(asset=self.asset, user=user, text="Test transcription 3")
        response = self.client.post(path)
        self.assertEqual(400, response.status_code)
        self.assertIn("error", response.json())

        # Test anonymous user after a rollback
        self.client.logout()
        transcription3 = create_transcription(
            asset=self.asset, user=user, text="Test transcription 3"
        )
        self.asset.rollback_transcription(user)
        with patch(
            "concordia.turnstile.fields.TurnstileField.validate", return_value=True
        ):
            response = self.client.post(path)
        response_json = response.json()
        self.assertEqual(201, response.status_code)
        self.assertIn("id", response_json)
        self.assertIn("text", response_json)
        self.assertEqual(response_json["text"], transcription3.text)
        self.assertIn("undo_available", response_json)
        self.assertEqual(response_json["undo_available"], True)
        self.assertIn("redo_available", response_json)
        self.assertEqual(response_json["redo_available"], False)

    def tearDown(self):
        post_save.connect(on_transcription_save, sender=Transcription)


@override_settings(
    CACHES={
        "visualization_cache": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
)
class VisualizationDataViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.cache = caches["visualization_cache"]
        VisualizationDataView.cache = self.cache
        self.cache.clear()
        self.view = VisualizationDataView.as_view()

    def test_get_missing_data_returns_404(self):
        # If no entry exists in the cache under the given name,
        # the view should return a 404 with a JSON error message.
        request = self.factory.get("/visualizations/data/missing-key/")
        response = self.view(request, name="missing-key")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response["Content-Type"], "application/json")
        data = json.loads(response.content)
        self.assertEqual(
            data, {"error": "No visualization data found for 'missing-key'"}
        )

    def test_get_existing_data_returns_200_and_json(self):
        # When the cache contains data for the given name,
        # the view should return it as JSON with status 200.
        sample_data = {"foo": "bar", "numbers": [1, 2, 3]}
        self.cache.set("sample-key", sample_data)
        request = self.factory.get("/visualizations/data/sample-key/")
        response = self.view(request, name="sample-key")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        data = json.loads(response.content)
        self.assertEqual(data, sample_data)
