from django.core.cache import caches
from django.test import TestCase, override_settings
from django.urls import reverse

from concordia.models import ProjectTopic, TranscriptionStatus

from .utils import (
    CreateTestUsers,
    JSONAssertMixin,
    create_asset,
    create_campaign,
    create_item,
    create_project,
    create_topic,
)


@override_settings(
    RATELIMIT_ENABLE=False,
    SESSION_ENGINE="django.contrib.sessions.backends.cache",
    CACHES={
        "default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"},
        "view_cache": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"},
    },
)
class TopicDetailViewTests(CreateTestUsers, JSONAssertMixin, TestCase):
    """
    Focused tests for the Topic detail view.
    """

    def setUp(self):
        for cache in caches.all():
            cache.clear()

    def tearDown(self):
        for cache in caches.all():
            cache.clear()

    def test_topic_detail_basic(self):
        topic = create_topic(title="GET Topic", slug="get-topic")
        response = self.client.get(reverse("topic-detail", args=(topic.slug,)))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/topic_detail.html"
        )
        self.assertContains(response, topic.title)

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

    def test_topic_detail_with_status_sets_querystring(self):
        """
        When a valid transcription_status is supplied, sublevel_querystring
        contains only that param.
        """
        topic = create_topic(title="GET Topic", slug="get-topic")
        response = self.client.get(
            reverse("topic-detail", args=(topic.slug,)),
            {"transcription_status": "not_started"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/topic_detail.html"
        )
        self.assertContains(response, topic.title)
        self.assertIn("sublevel_querystring", response.context)
        self.assertEqual(
            response.context["sublevel_querystring"], "transcription_status=not_started"
        )

    def test_url_filter_links_without_sublevel_querystring(self):
        """
        With a project-level url_filter and no sublevel filter, links for that
        project include transcription_status=<url_filter>, while projects without
        a url_filter do not include a transcription_status param.
        """
        topic = create_topic(title="Filter Topic", slug="filter-topic")
        campaign = create_campaign(title="Filter Test Campaign", slug="filter-test")

        project_with_filter = create_project(
            campaign=campaign, title="Project With Filter", slug="with-filter"
        )
        project_without_filter = create_project(
            campaign=campaign, title="Project Without Filter", slug="without-filter"
        )

        ProjectTopic.objects.create(
            project=project_with_filter,
            topic=topic,
            url_filter=TranscriptionStatus.SUBMITTED,
        )
        ProjectTopic.objects.create(
            project=project_without_filter,
            topic=topic,
            url_filter=None,
        )

        response = self.client.get(reverse("topic-detail", args=(topic.slug,)))
        self.assertEqual(response.status_code, 200)

        # project_with_filter has ?transcription_status=submitted
        # (appears twice: image+title)
        self.assertContains(
            response,
            f"/campaigns/{campaign.slug}/{project_with_filter.slug}/?transcription_status=submitted",
            2,
        )
        # project_without_filter should not include any transcription_status param
        self.assertNotContains(
            response,
            f"/campaigns/{campaign.slug}/{project_without_filter.slug}/?transcription_status=",
        )

    def test_sublevel_querystring_only_keeps_transcription_status(self):
        """
        If extra params are provided along with transcription_status, only
        transcription_status is retained in sublevel_querystring.
        """
        topic = create_topic(title="GET Topic", slug="get-topic")
        response = self.client.get(
            reverse("topic-detail", args=(topic.slug,)),
            {"transcription_status": "not_started", "another_param": "some_value"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("sublevel_querystring", response.context)
        self.assertEqual(
            response.context["sublevel_querystring"], "transcription_status=not_started"
        )

    def test_with_status_and_no_assets_excludes_projects(self):
        """
        When a transcription_status is present and projects have no assets,
        those projects are excluded (no links rendered).
        """
        topic = create_topic(title="Filter Topic", slug="filter-topic")
        campaign = create_campaign(title="Filter Test Campaign", slug="filter-test")

        project_with_filter = create_project(
            campaign=campaign, title="Project With Filter", slug="with-filter"
        )
        project_without_filter = create_project(
            campaign=campaign, title="Project Without Filter", slug="without-filter"
        )

        ProjectTopic.objects.create(
            project=project_with_filter,
            topic=topic,
            url_filter=TranscriptionStatus.SUBMITTED,
        )
        ProjectTopic.objects.create(
            project=project_without_filter,
            topic=topic,
            url_filter=None,
        )

        response = self.client.get(
            reverse("topic-detail", args=(topic.slug,)),
            {"transcription_status": "not_started", "another_param": "some_value"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("sublevel_querystring", response.context)
        self.assertEqual(
            response.context["sublevel_querystring"], "transcription_status=not_started"
        )

        # No assets exist, so neither project should appear with the filter applied
        self.assertContains(
            response,
            f"/campaigns/{campaign.slug}/{project_with_filter.slug}/?transcription_status=not_started",
            0,
        )
        self.assertContains(
            response,
            f"/campaigns/{campaign.slug}/{project_without_filter.slug}/?transcription_status=not_started",
            0,
        )

    def test_with_status_and_assets_uses_sublevel_and_overrides_url_filter(self):
        """
        When assets exist and a transcription_status is supplied, projects with no
        url_filter are shown using the sublevel filter. Projects with a url_filter
        that does not match the sublevel filter are excluded.
        """
        topic = create_topic(title="Filter Topic", slug="filter-topic")
        campaign = create_campaign(title="Filter Test Campaign", slug="filter-test")

        project_with_filter = create_project(
            campaign=campaign, title="Project With Filter", slug="with-filter"
        )
        project_without_filter = create_project(
            campaign=campaign, title="Project Without Filter", slug="without-filter"
        )

        ProjectTopic.objects.create(
            project=project_with_filter,
            topic=topic,
            url_filter=TranscriptionStatus.SUBMITTED,
        )
        ProjectTopic.objects.create(
            project=project_without_filter,
            topic=topic,
            url_filter=None,
        )

        # Add assets so eligible projects will display
        item_with_filter = create_item(project=project_with_filter)
        create_asset(item=item_with_filter)
        item_without_filter = create_item(project=project_without_filter)
        create_asset(item=item_without_filter)

        response = self.client.get(
            reverse("topic-detail", args=(topic.slug,)),
            {"transcription_status": "not_started", "another_param": "some_value"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("sublevel_querystring", response.context)
        self.assertEqual(
            response.context["sublevel_querystring"], "transcription_status=not_started"
        )

        # Project WITH a mismatching url_filter should be excluded
        self.assertContains(
            response,
            f"/campaigns/{campaign.slug}/{project_with_filter.slug}/?transcription_status=not_started",
            0,
        )

        # Project WITHOUT a url_filter should use the sublevel filter
        # (appears twice: image + title)
        self.assertContains(
            response,
            f"/campaigns/{campaign.slug}/{project_without_filter.slug}/?transcription_status=not_started",
            2,
        )

    def test_with_status_and_assets_includes_matching_url_filter(self):
        """
        When assets exist and a transcription_status is supplied, projects with a
        matching url_filter should be included, and links should use that status.
        """
        topic = create_topic(title="Filter Topic", slug="filter-topic")
        campaign = create_campaign(title="Filter Test Campaign", slug="filter-test")

        project_with_filter = create_project(
            campaign=campaign, title="Project With Filter", slug="with-filter"
        )
        project_without_filter = create_project(
            campaign=campaign, title="Project Without Filter", slug="without-filter"
        )

        ProjectTopic.objects.create(
            project=project_with_filter,
            topic=topic,
            url_filter=TranscriptionStatus.SUBMITTED,
        )
        ProjectTopic.objects.create(
            project=project_without_filter,
            topic=topic,
            url_filter=None,
        )

        # Ensure both projects have at least one asset counted as "submitted"
        item_with_filter = create_item(project=project_with_filter)
        a1 = create_asset(item=item_with_filter)
        a1.transcription_status = TranscriptionStatus.SUBMITTED
        a1.save(update_fields=["transcription_status"])

        item_without_filter = create_item(project=project_without_filter)
        a2 = create_asset(item=item_without_filter)
        a2.transcription_status = TranscriptionStatus.SUBMITTED
        a2.save(update_fields=["transcription_status"])

        response = self.client.get(
            reverse("topic-detail", args=(topic.slug,)),
            {"transcription_status": "submitted"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("sublevel_querystring", response.context)
        self.assertEqual(
            response.context["sublevel_querystring"], "transcription_status=submitted"
        )

        # Project WITH a matching url_filter should be included (2 links: image + title)
        self.assertContains(
            response,
            f"/campaigns/{campaign.slug}/{project_with_filter.slug}/?transcription_status=submitted",
            2,
        )

        # Project WITHOUT a url_filter should also be included (also 2 links)
        self.assertContains(
            response,
            f"/campaigns/{campaign.slug}/{project_without_filter.slug}/?transcription_status=submitted",
            2,
        )

    def test_topic_detail_with_invalid_status_ignores_filter(self):
        """
        If transcription_status is present but invalid, the view should treat it
        as absent: no filtering by status and no sublevel_querystring.
        """
        topic = create_topic(title="Filter Topic", slug="filter-topic")
        campaign = create_campaign(title="Filter Test Campaign", slug="filter-test")

        project_with_filter = create_project(
            campaign=campaign, title="Project With Filter", slug="with-filter"
        )
        project_without_filter = create_project(
            campaign=campaign, title="Project Without Filter", slug="without-filter"
        )

        ProjectTopic.objects.create(
            project=project_with_filter,
            topic=topic,
            url_filter=TranscriptionStatus.SUBMITTED,
        )
        ProjectTopic.objects.create(
            project=project_without_filter,
            topic=topic,
            url_filter=None,
        )

        # Make both projects eligible to display
        create_asset(item=create_item(project=project_with_filter))
        create_asset(item=create_item(project=project_without_filter))

        # Supply an invalid status
        response = self.client.get(
            reverse("topic-detail", args=(topic.slug,)),
            {"transcription_status": "not-a-real-status", "another_param": "x"},
        )
        self.assertEqual(response.status_code, 200)

        # sublevel_querystring should be empty (invalid status ignored)
        self.assertIn("sublevel_querystring", response.context)
        self.assertEqual(response.context["sublevel_querystring"], "")

        # Project WITH a url_filter should use its own filter in links
        self.assertContains(
            response,
            f"/campaigns/{campaign.slug}/{project_with_filter.slug}/?transcription_status=submitted",
            2,
        )
        # Project WITHOUT a url_filter should not include a transcription_status param
        self.assertNotContains(
            response,
            f"/campaigns/{campaign.slug}/{project_without_filter.slug}/?transcription_status=",
        )

    def test_url_filter_empty_string_treated_as_missing(self):
        topic = create_topic(title="Filter Topic", slug="filter-topic")
        campaign = create_campaign(title="Filter Test Campaign", slug="filter-test")

        project_empty_filter = create_project(
            campaign=campaign, title="Project Empty Filter", slug="empty-filter"
        )
        project_none_filter = create_project(
            campaign=campaign, title="Project None Filter", slug="none-filter"
        )

        ProjectTopic.objects.create(
            project=project_empty_filter, topic=topic, url_filter=""
        )
        ProjectTopic.objects.create(
            project=project_none_filter, topic=topic, url_filter=None
        )

        # Make both eligible
        item_empty = create_item(project=project_empty_filter)
        asset_empty = create_asset(item=item_empty)
        item_none = create_item(project=project_none_filter)
        asset_none = create_asset(item=item_none)

        # no sublevel filter, so neither link should have transcription_status
        resp1 = self.client.get(reverse("topic-detail", args=(topic.slug,)))
        self.assertEqual(resp1.status_code, 200)
        self.assertNotContains(
            resp1,
            f"/campaigns/{campaign.slug}/{project_empty_filter.slug}/?transcription_status=",
        )
        self.assertNotContains(
            resp1,
            f"/campaigns/{campaign.slug}/{project_none_filter.slug}/?transcription_status=",
        )

        # Set at least one asset to SUBMITTED for each project (so they’re not excluded)
        asset_empty.transcription_status = TranscriptionStatus.SUBMITTED
        asset_empty.save(update_fields=["transcription_status"])

        asset_none.transcription_status = TranscriptionStatus.SUBMITTED
        asset_none.save(update_fields=["transcription_status"])

        # valid sublevel filter, so both included and use that status in links
        resp2 = self.client.get(
            reverse("topic-detail", args=(topic.slug,)),
            {"transcription_status": "submitted"},
        )
        self.assertEqual(resp2.status_code, 200)
        self.assertContains(
            resp2,
            f"/campaigns/{campaign.slug}/{project_empty_filter.slug}/?transcription_status=submitted",
            2,
        )
        self.assertContains(
            resp2,
            f"/campaigns/{campaign.slug}/{project_none_filter.slug}/?transcription_status=submitted",
            2,
        )
