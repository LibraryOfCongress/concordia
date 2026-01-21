"""
Tests for for the top-level & “CMS” views
"""

from unittest.mock import patch

from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.urls import reverse
from maintenance_mode.core import get_maintenance_mode, set_maintenance_mode

from concordia.models import (
    Banner,
    CarouselSlide,
    Guide,
    OverlayPosition,
    SimplePage,
    SiteReport,
)
from concordia.views.simple_pages import simple_page

from .utils import (
    CacheControlAssertions,
    CreateTestUsers,
    JSONAssertMixin,
    create_guide,
    create_site_report,
)


class TopLevelViewTests(
    JSONAssertMixin, CreateTestUsers, CacheControlAssertions, TestCase
):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_healthz(self):
        data = self.assertValidJSON(self.client.get("/healthz"))

        for k in (
            "current_time",
            "load_average",
            "debug",
            "database_has_data",
            "application_version",
        ):
            self.assertIn(k, data)

    def test_homepage(self):
        response = self.client.get(reverse("homepage"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home.html")

        banner = Banner.objects.create(
            slug="test-banner", text="Test Banner", active=True
        )
        response = self.client.get(reverse("homepage"))
        context = response.context
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home.html")
        self.assertIn("banner", context)
        self.assertEqual(context["banner"].text, banner.text)
        banner.delete()

        slide = CarouselSlide.objects.create(
            published=True,
            overlay_position=OverlayPosition.LEFT,
            headline="Test Headline",
        )
        response = self.client.get(reverse("homepage"))
        context = response.context
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home.html")
        self.assertIn("firstslide", context)
        self.assertEqual(context["firstslide"].headline, slide.headline)
        slide.delete()

    def test_contact_us_redirect(self):
        response = self.client.get(reverse("contact"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://ask.loc.gov/crowd")

    def test_simple_page(self):
        s = SimplePage.objects.create(
            title="Get Started 123",
            body="not the real body",
            path=reverse("welcome-guide"),
        )

        s2 = SimplePage.objects.create(
            title="Get Started Spanish 123",
            body="not the real spanish body",
            path=reverse("welcome-guide-spanish"),
        )

        resp = self.client.get(reverse("welcome-guide"))
        self.assertEqual(200, resp.status_code)
        self.assertEqual(s.title, resp.context["title"])
        self.assertEqual(
            [(reverse("welcome-guide"), s.title)], resp.context["breadcrumbs"]
        )
        self.assertEqual(resp.context["body"], f"<p>{s.body}</p>")

        request = RequestFactory().get("/")
        resp = simple_page(request, path=reverse("welcome-guide"))
        self.assertEqual(200, resp.status_code)

        resp = self.client.get(reverse("welcome-guide-spanish"))
        self.assertEqual(200, resp.status_code)
        self.assertEqual(s2.title, resp.context["title"])
        self.assertEqual("es", resp.context["language_code"])
        self.assertEqual(
            [(reverse("welcome-guide-spanish"), s2.title)], resp.context["breadcrumbs"]
        )
        self.assertEqual(resp.context["body"], f"<p>{s2.body}</p>")

    def test_nested_simple_page(self):
        Guide.objects.create(title="How to Tag")
        l1 = SimplePage.objects.create(
            title="Get Started",
            body="not the real body",
            path=reverse("welcome-guide"),
        )

        l2 = SimplePage.objects.create(
            title="How to Tag",
            body="This is _not_ the real page",
            path=reverse("how-to-tag"),
        )

        resp = self.client.get(reverse("how-to-tag"))
        self.assertEqual(200, resp.status_code)
        self.assertEqual(l2.title, resp.context["title"])
        self.assertEqual(
            resp.context["breadcrumbs"],
            [(reverse("welcome-guide"), l1.title), (reverse("how-to-tag"), l2.title)],
        )
        self.assertHTMLEqual(
            resp.context["body"], "<p>This is <em>not</em> the real page</p>"
        )

        create_guide(page=l1)
        resp = self.client.get(reverse("welcome-guide"))
        self.assertEqual(200, resp.status_code)

    def test_simple_page_with_context(self):
        path = reverse("about")
        page_body = (
            "<p>{{ assets_published}}</p> "
            "<p>{{ campaigns_published }}</p> "
            "<p>{{ assets_completed }}</p> "
            "<p>{{ assets_waiting_review }}</p> "
            "<p>{{ users_activated }}</p>"
        )
        about_page = SimplePage.objects.create(
            title="About",
            body=page_body,
            path=reverse("about"),
        )

        # Test with no SiteReports
        response = self.client.get(path)
        context = response.context
        self.assertEqual(200, response.status_code)
        self.assertEqual(about_page.title, context["title"])
        self.assertEqual([(path, about_page.title)], context["breadcrumbs"])
        self.assertEqual(
            context["body"], "<p>0</p>\n<p>0</p>\n<p>0</p>\n<p>0</p>\n<p>0</p>"
        )

        # Test with only active SiteReport
        cache.clear()
        create_site_report(
            report_name=SiteReport.ReportName.TOTAL,
            campaigns_published=1,
            assets_published=1,
            assets_completed=1,
            assets_waiting_review=1,
            users_activated=1,
        )

        response = self.client.get(path)
        context = response.context
        self.assertEqual(
            context["body"], "<p>1</p>\n<p>1</p>\n<p>1</p>\n<p>1</p>\n<p>1</p>"
        )

        # Test with both SiteReports, but with cached values from above
        # So we should expect the retired SiteReport to not be included in data
        create_site_report(
            report_name=SiteReport.ReportName.RETIRED_TOTAL,
            assets_published=1,
            assets_completed=1,
            assets_waiting_review=1,
        )

        response = self.client.get(path)
        context = response.context
        self.assertEqual(
            context["body"], "<p>1</p>\n<p>1</p>\n<p>1</p>\n<p>1</p>\n<p>1</p>"
        )

        # Test without bad cached data
        cache.clear()
        response = self.client.get(path)
        context = response.context
        self.assertEqual(
            context["body"], "<p>2</p>\n<p>1</p>\n<p>2</p>\n<p>2</p>\n<p>1</p>"
        )


class HelpCenterRedirectTests(TestCase):
    def test_HelpCenterRedirectView(self):
        SimplePage.objects.create(
            title="Get Started Page",
            body="Page Body",
            path="/get-started/page/",
        )

        self.assertRedirects(
            self.client.get("/help-center/page/"), "/get-started/page/"
        )

    def test_HelpCenterSpanishRedirectView(self):
        SimplePage.objects.create(
            title="Get Started Page",
            body="Page Body",
            path="/get-started-esp/page-esp/",
        )

        self.assertRedirects(
            self.client.get("/help-center/page-esp/"), "/get-started-esp/page-esp/"
        )


class MaintenanceModeTests(TestCase, CreateTestUsers):
    def setUp(self):
        cache.clear()
        self.timestamp_value = 1
        self.user = None

    def tearDown(self):
        cache.clear()

    def test_maintenance_mode_off(self):
        self.user = self.create_super_user()
        self.login_user()
        set_maintenance_mode(True)

        with patch("concordia.views.maintenance_mode.time") as mock:
            mock.return_value = self.timestamp_value
            self.assertRedirects(
                self.client.get(reverse("maintenance_mode_off")),
                f"/?t={self.timestamp_value}",
            )
        self.assertEqual(get_maintenance_mode(), False)

        self.user = self.create_test_user()
        self.login_user()
        set_maintenance_mode(True)
        with patch("concordia.views.maintenance_mode.time") as mock:
            mock.return_value = self.timestamp_value
            self.assertRedirects(
                self.client.get(reverse("maintenance_mode_off")),
                f"/?t={self.timestamp_value}",
                target_status_code=503,
            )
        self.assertEqual(get_maintenance_mode(), True)

    def test_maintenance_mode_on_without_frontend(self):
        cache.set("maintenance_mode_frontend_available", False, None)

        self.user = self.create_super_user()
        self.login_user()
        set_maintenance_mode(False)
        with patch("concordia.views.maintenance_mode.time") as mock:
            mock.return_value = self.timestamp_value
            self.assertRedirects(
                self.client.get(reverse("maintenance_mode_on")),
                f"/?t={self.timestamp_value}",
                target_status_code=503,
            )
        self.assertEqual(get_maintenance_mode(), True)

        self.user = self.create_test_user()
        self.login_user()
        set_maintenance_mode(False)
        with patch("concordia.views.maintenance_mode.time") as mock:
            mock.return_value = self.timestamp_value
            self.assertRedirects(
                self.client.get(reverse("maintenance_mode_on")),
                f"/?t={self.timestamp_value}",
            )
        self.assertEqual(get_maintenance_mode(), False)

    def test_maintenance_mode_on_with_frontend(self):
        cache.set("maintenance_mode_frontend_available", True, None)

        self.user = self.create_super_user()
        self.login_user()
        set_maintenance_mode(False)
        with patch("concordia.views.maintenance_mode.time") as mock:
            mock.return_value = self.timestamp_value
            self.assertRedirects(
                self.client.get(reverse("maintenance_mode_on")),
                f"/?t={self.timestamp_value}",
            )
        self.assertEqual(get_maintenance_mode(), True)

        self.user = self.create_test_user()
        self.login_user()
        set_maintenance_mode(False)
        with patch("concordia.views.maintenance_mode.time") as mock:
            mock.return_value = self.timestamp_value
            self.assertRedirects(
                self.client.get(reverse("maintenance_mode_on")),
                f"/?t={self.timestamp_value}",
            )
        self.assertEqual(get_maintenance_mode(), False)

    def test_maintenance_mode_frontend_available(self):
        self.user = self.create_super_user()
        self.login_user()
        cache.set("maintenance_mode_frontend_available", False, None)
        with patch("concordia.views.maintenance_mode.time") as mock:
            mock.return_value = self.timestamp_value
            self.assertRedirects(
                self.client.get(reverse("maintenance_mode_frontend_available")),
                f"/?t={self.timestamp_value}",
            )
        self.assertEqual(cache.get("maintenance_mode_frontend_available"), True)

        self.user = self.create_test_user()
        self.login_user()
        cache.set("maintenance_mode_frontend_available", False, None)
        with patch("concordia.views.maintenance_mode.time") as mock:
            mock.return_value = self.timestamp_value
            self.assertRedirects(
                self.client.get(reverse("maintenance_mode_frontend_available")),
                f"/?t={self.timestamp_value}",
            )
        self.assertEqual(cache.get("maintenance_mode_frontend_available"), False)

    def test_maintenance_mode_frontend_unavailable(self):
        self.user = self.create_super_user()
        self.login_user()
        cache.set("maintenance_mode_frontend_available", True, None)
        with patch("concordia.views.maintenance_mode.time") as mock:
            mock.return_value = self.timestamp_value
            self.assertRedirects(
                self.client.get(reverse("maintenance_mode_frontend_unavailable")),
                f"/?t={self.timestamp_value}",
            )
        self.assertEqual(cache.get("maintenance_mode_frontend_available"), False)

        self.user = self.create_test_user()
        self.login_user()
        cache.set("maintenance_mode_frontend_available", True, None)
        with patch("concordia.views.maintenance_mode.time") as mock:
            mock.return_value = self.timestamp_value
            self.assertRedirects(
                self.client.get(reverse("maintenance_mode_frontend_unavailable")),
                f"/?t={self.timestamp_value}",
            )
        self.assertEqual(cache.get("maintenance_mode_frontend_available"), True)
