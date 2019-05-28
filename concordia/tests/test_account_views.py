"""
Tests for user account-related views
"""
from django.test import TestCase, override_settings
from django.urls import reverse

from concordia.models import User

from .utils import JSONAssertMixin


@override_settings(RATELIMIT_ENABLE=False)
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
