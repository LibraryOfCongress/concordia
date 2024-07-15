"""
Tests for user account-related views
"""

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from concordia.models import ConcordiaUser, User

from .utils import (
    CacheControlAssertions,
    CreateTestUsers,
    JSONAssertMixin,
    create_campaign,
)


@override_settings(RATELIMIT_ENABLE=False)
class ConcordiaViewTests(
    CreateTestUsers, JSONAssertMixin, CacheControlAssertions, TestCase
):
    """
    This class contains the unit tests for the view in the concordia app.
    """

    def test_AccountProfileView_get(self):
        """
        Test the http GET on route account/profile
        """

        self.login_user()

        response = self.client.get(reverse("user-profile"))

        self.assertEqual(response.status_code, 200)
        self.assertUncacheable(response)
        self.assertTemplateUsed(response, template_name="account/profile.html")

        self.assertEqual(response.context["user"], self.user)
        self.assertContains(response, self.user.username)
        self.assertContains(response, self.user.email)

    def test_AccountProfileView_post(self):
        """
        This unit test tests the post entry for the route account/profile
        :param self:
        """
        test_email = "tester2@example.com"

        self.login_user()

        with self.settings(REQUIRE_EMAIL_RECONFIRMATION=False):
            response = self.client.post(
                reverse("user-profile"), {"email": test_email, "username": "tester"}
            )

            self.assertEqual(response.status_code, 302)
            self.assertUncacheable(response)
            index = response.url.find("#")
            self.assertEqual(response.url[:index], reverse("user-profile"))

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
        self.assertUncacheable(response)

        # Verify the User was not changed
        updated_user = User.objects.get(id=self.user.id)
        self.assertEqual(updated_user.first_name, "")

    def test_ajax_session_status_anon(self):
        response = self.client.get(reverse("ajax-session-status"))
        self.assertCachePrivate(response)
        data = self.assertValidJSON(response)
        self.assertEqual(data, {})

    def test_ajax_session_status(self):
        self.login_user()

        response = self.client.get(reverse("ajax-session-status"))
        self.assertCachePrivate(response)
        data = self.assertValidJSON(response)

        self.assertIn("links", data)
        self.assertIn("username", data)

        self.assertEqual(data["username"], self.user.username)

        self.assertFalse(any(link["title"] == "Admin Area" for link in data["links"]))

    def test_ajax_session_status_staff(self):
        self.login_user(is_staff=True, is_superuser=True)

        response = self.client.get(reverse("ajax-session-status"))
        self.assertCachePrivate(response)
        data = self.assertValidJSON(response)

        self.assertIn("links", data)
        self.assertIn("username", data)

        self.assertEqual(data["username"], self.user.username)

        self.assertTrue(any(link["title"] == "Admin Area" for link in data["links"]))

    def test_ajax_messages(self):
        self.login_user()

        response = self.client.get(reverse("ajax-messages"))
        data = self.assertValidJSON(response)

        self.assertIn("messages", data)

        # This view cannot be cached because the messages would be displayed
        # multiple times:
        self.assertUncacheable(response)

    def test_email_reconfirmation(self):
        self.login_user()
        # Confirm the user doesn't have a reconfirmation key
        concordia_user = ConcordiaUser.objects.get(id=self.user.id)
        with self.assertRaises(ValueError):
            concordia_user.get_email_reconfirmation_key()

        with self.settings(REQUIRE_EMAIL_RECONFIRMATION=True):
            email_data = {"email": "change@example.com"}
            response = self.client.post(reverse("user-profile"), email_data)
            self.assertRedirects(response, "{}#account".format(reverse("user-profile")))
            self.assertTemplateUsed(response, "emails/email_reconfirmation_subject.txt")
            self.assertTemplateUsed(response, "emails/email_reconfirmation_body.txt")
            self.assertEqual(len(mail.outbox), 1)
            mail.outbox = []

            updated_user = User.objects.get(id=self.user.id)
            self.assertNotEqual(updated_user.email, email_data["email"])

            concordia_user = ConcordiaUser.objects.get(id=self.user.id)

            self.assertEqual(
                concordia_user.get_email_for_reconfirmation(), email_data["email"]
            )
            confirmation_key = concordia_user.get_email_reconfirmation_key()
            confirmation_response = self.client.get(
                reverse(
                    "email-reconfirmation",
                    kwargs={"confirmation_key": confirmation_key},
                )
            )
            self.assertRedirects(
                confirmation_response, "{}#account".format(reverse("user-profile"))
            )
            updated_user = User.objects.get(id=self.user.id)
            self.assertEqual(updated_user.email, email_data["email"])

            error_response = self.client.get(
                reverse(
                    "email-reconfirmation",
                    kwargs={"confirmation_key": confirmation_key},
                )
            )
            self.assertEqual(error_response.status_code, 403)
            self.assertTemplateUsed(
                error_response, "account/email_reconfirmation_failed.html"
            )

        with self.settings(REQUIRE_EMAIL_RECONFIRMATION=False):
            email_data = {"email": "change2@example.com"}
            response = self.client.post(reverse("user-profile"), email_data)
            self.assertRedirects(response, "{}#account".format(reverse("user-profile")))
            self.assertEqual(len(mail.outbox), 0)
            updated_user = User.objects.get(id=self.user.id)
            self.assertEqual(updated_user.email, email_data["email"])

    def test_AccountLetterView(self):
        self.login_user()

        response = self.client.get(reverse("user-letter"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Disposition"], "attachment; filename=letter.pdf"
        )
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_get_pages(self):
        self.login_user()
        create_campaign()
        url = reverse("get_pages")

        response = self.client.get(url, {"activity": "transcribed"})
        self.assertEqual(response.status_code, 200)

        response = self.client.get(
            url, {"activity": "reviewed", "order_by": "date-ascending"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertUncacheable(response)

        response = self.client.get(url, {"status": ["completed"], "campaign": 1})
        self.assertEqual(response.status_code, 200)
        self.assertUncacheable(response)

        response = self.client.get(url, {"status": ["in_progress", "submitted"]})
        self.assertEqual(response.status_code, 200)
        self.assertUncacheable(response)

        response = self.client.get(
            url, kwargs={"start": "1900-01-01", "end": "1999-12-31"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertUncacheable(response)

        response = self.client.get(url, {"end": "1999-12-31"})
        self.assertEqual(response.status_code, 200)
        self.assertUncacheable(response)

        response = self.client.get(url, {"start": "1900-01-01", "end": "1999-12-31"})
        self.assertEqual(response.status_code, 200)
        self.assertUncacheable(response)
