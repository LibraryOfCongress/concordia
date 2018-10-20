# TODO: Add correct copyright header

from django.test import TestCase
from django.urls import reverse


class ViewTest_1st_level(TestCase):
    """
    This is a test case for testing all the first level views originated
    from home pages.

    """

    def test_contact_us_get(self):

        response = self.client.get(reverse("contact"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "contact.html")

    def test_contact_us_get_pre_populate(self):
        test_http_referrer = "http://foo/bar"

        response = self.client.get(reverse("contact"), HTTP_REFERER=test_http_referrer)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "contact.html")

        self.assertEqual(
            response.context["form"].initial["referrer"], test_http_referrer
        )

    def test_contact_us_post(self):
        post_data = {
            "email": "nobody@example.com",
            "subject": "Problem found",
            "link": "http://www.loc.gov/nowhere",
            "story": "Houston, we got a problem",
        }

        response = self.client.post(reverse("contact"), post_data)

        self.assertEqual(response.status_code, 302)

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
