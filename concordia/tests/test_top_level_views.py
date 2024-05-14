"""
Tests for for the top-level & “CMS” views
"""

from django.test import RequestFactory, TestCase
from django.urls import reverse

from concordia.models import Guide, SimplePage
from concordia.views import simple_page

from .utils import CacheControlAssertions, CreateTestUsers, JSONAssertMixin


class TopLevelViewTests(
    JSONAssertMixin, CreateTestUsers, CacheControlAssertions, TestCase
):
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

    def test_contact_us_get(self):
        response = self.client.get(reverse("contact"))

        self.assertEqual(response.status_code, 200)
        self.assertUncacheable(response)
        self.assertTemplateUsed(response, "contact.html")

    def test_contact_us_with_referrer(self):
        test_http_referrer = "http://foo/bar"

        response = self.client.get(reverse("contact"), HTTP_REFERER=test_http_referrer)

        self.assertEqual(response.status_code, 200)
        self.assertUncacheable(response)
        self.assertTemplateUsed(response, "contact.html")

        self.assertEqual(
            response.context["form"].initial["referrer"], test_http_referrer
        )

    def test_contact_us_as_a_logged_in_user(self):
        """
        The contact form should pre-fill your email address if you're logged in
        """

        self.login_user()

        response = self.client.get(reverse("contact"))

        self.assertEqual(response.status_code, 200)
        self.assertUncacheable(response)
        self.assertTemplateUsed(response, "contact.html")

        self.assertEqual(response.context["form"].initial["email"], self.user.email)

    def test_contact_us_post(self):
        post_data = {
            "email": "nobody@example.com",
            "subject": "Problem found",
            "link": "http://www.loc.gov/nowhere",
            "story": "Houston, we got a problem",
        }

        response = self.client.post(reverse("contact"), post_data)

        self.assertEqual(response.status_code, 302)
        self.assertUncacheable(response)

    def test_contact_us_post_invalid(self):
        post_data = {
            "email": "nobody@",
            "subject": "Problem found",
            "story": "Houston, we got a problem",
        }

        response = self.client.post(reverse("contact"), post_data)

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            {"email": ["Enter a valid email address."]}, response.context["form"].errors
        )

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

        request = RequestFactory().get(reverse("welcome-guide"))
        request.path = reverse("welcome-guide")
        resp = simple_page(request)
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
