"""
Tests for user account-related views
"""
from django.test import TestCase, override_settings
from django.urls import reverse

from concordia.models import User

from .utils import CacheControlAssertions, CreateTestUsers, JSONAssertMixin


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
        test_email = "tester@example.com"

        self.login_user()

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

    def test_ajax_messages(self):
        self.login_user()

        response = self.client.get(reverse("ajax-messages"))
        data = self.assertValidJSON(response)

        self.assertIn("messages", data)

        # This view cannot be cached because the messages would be displayed
        # multiple times:
        self.assertUncacheable(response)
