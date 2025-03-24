"""
Tests for user account-related views
"""

from smtplib import SMTPException
from unittest.mock import patch

from django import forms
from django.contrib.messages import get_messages
from django.core import mail, signing
from django.core.cache import cache
from django.db.models.signals import post_save
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.timezone import now

from concordia.models import ConcordiaUser, Transcription, User
from concordia.signals.handlers import on_transcription_save
from concordia.utils import get_anonymous_user

from .utils import (
    CacheControlAssertions,
    CreateTestUsers,
    JSONAssertMixin,
    create_asset,
    create_campaign,
    create_transcription,
    create_user_profile_activity,
)


@override_settings(RATELIMIT_ENABLE=False)
class ConcordiaAccountViewTests(
    CreateTestUsers, JSONAssertMixin, CacheControlAssertions, TestCase
):
    """
    This class contains the unit tests for the view in the concordia app.
    """

    def setUp(self):
        post_save.disconnect(on_transcription_save, sender=Transcription)
        cache.clear()

    def tearDown(self):
        cache.clear()

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

        response = self.client.get(reverse("user-profile"), {"activity": "transcribed"})
        self.assertEqual(response.status_code, 200)
        self.assertUncacheable(response)
        self.assertTemplateUsed(response, template_name="account/profile.html")
        self.assertEqual(response.context["user"], self.user)
        self.assertEqual(response.context["active_tab"], "recent")

        response = self.client.get(reverse("user-profile"), {"status": "submitted"})
        self.assertEqual(response.status_code, 200)
        self.assertUncacheable(response)
        self.assertTemplateUsed(response, template_name="account/profile.html")
        self.assertEqual(response.context["user"], self.user)
        self.assertEqual(response.context["active_tab"], "recent")
        self.assertEqual(response.context["status_list"], ["submitted"])

        response = self.client.get(
            reverse("user-profile"), {"start": "1970-01-01", "end": "1970-01-02"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertUncacheable(response)
        self.assertTemplateUsed(response, template_name="account/profile.html")
        self.assertEqual(response.context["user"], self.user)
        self.assertEqual(response.context["end"], "1970-01-02")
        self.assertEqual(response.context["start"], "1970-01-01")

        anon = get_anonymous_user()
        asset = create_asset()
        t = asset.transcription_set.create(asset=asset, user=anon)
        t.submitted = now()
        t.accepted = now()
        t.reviewed_by = self.user
        t.save()
        user_profile_activity = create_user_profile_activity(
            campaign=asset.item.project.campaign, user=self.user
        )
        user_profile_activity.review_count = 1
        user_profile_activity.save()
        response = self.client.get(reverse("user-profile"))
        self.assertEqual(response.status_code, 200)
        self.assertUncacheable(response)
        self.assertTemplateUsed(response, template_name="account/profile.html")
        self.assertEqual(response.context["user"], self.user)
        self.assertEqual(response.context["totalReviews"], 1)
        self.assertEqual(response.context["totalCount"], 1)

    def test_AccountProfileView_post(self):
        """
        This unit test tests the post entry for the route account/profile
        :param self:
        """
        test_email = "tester2@example.com"

        self.login_user()

        with self.settings(REQUIRE_EMAIL_RECONFIRMATION=False):
            # First, test trying to 'update' to the already used email
            response = self.client.post(
                reverse("user-profile"),
                {"email": self.user.email, "username": "tester"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)
        self.assertFalse(response.context["form"].is_valid())

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

        # Test first/last name can be updated
        self.assertNotEqual(updated_user.first_name, "Test")
        self.assertNotEqual(updated_user.last_name, "User")
        response = self.client.post(
            reverse("user-profile"),
            {"submit_name": True, "first_name": "Test", "last_name": "User"},
        )

        self.assertRedirects(response, reverse("user-profile"))
        self.assertUncacheable(response)

        updated_user = User.objects.get(email=test_email)
        first_name = updated_user.first_name
        last_name = updated_user.last_name
        self.assertEqual(first_name, "Test")
        self.assertEqual(last_name, "User")

        # Test name form submission without valid data
        # First/last names should stay the same after post
        # The form can't really be invalid since even blank
        # values just set the names to empty strings,
        # so we need to mock an invalid response
        with patch("concordia.forms.UserNameForm.is_valid") as mock:
            mock.return_value = False
            response = self.client.post(reverse("user-profile"), {"submit_name": True})
        updated_user = User.objects.get(email=test_email)
        self.assertEqual(updated_user.first_name, first_name)
        self.assertEqual(updated_user.last_name, last_name)

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
            with patch("django.core.mail.EmailMultiAlternatives.send") as mock:
                mock.side_effect = SMTPException()
                response = self.client.post(reverse("user-profile"), email_data)
                self.assertRedirects(
                    response, "{}#account".format(reverse("user-profile"))
                )
                messages = [
                    str(message) for message in get_messages(response.wsgi_request)
                ]
                self.assertIn(
                    "Email confirmation could not be sent.",
                    messages,
                )
                self.assertEqual(len(mail.outbox), 0)

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

            # Check if user failing validation is handled
            with patch("concordia.models.ConcordiaUser.full_clean") as mock:
                mock.side_effect = forms.ValidationError("Testing error")
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

            # Check if invalid data from confirmation key is handled
            with patch("django.core.signing.loads") as mock:
                mock.return_value = {
                    "username": "bad-username",
                    "email": "bad-email-address",
                }
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

            # Check if signing errors are handled
            with patch("django.core.signing.loads") as mock:
                mock.side_effect = signing.BadSignature()
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

                mock.side_effect = signing.SignatureExpired()
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
        campaign = create_campaign()
        url = reverse("get_pages")

        response = self.client.get(url, {"activity": "transcribed"})
        self.assertEqual(response.status_code, 200)

        response = self.client.get(
            url, {"activity": "reviewed", "order_by": "date-ascending"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertUncacheable(response)

        response = self.client.get(
            url, {"status": ["completed"], "campaign": campaign.id}
        )
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

    def test_AccountDeletionView(self):
        self.login_user()

        response = self.client.get(reverse("account-deletion"))
        self.assertEqual(response.status_code, 200)
        self.assertUncacheable(response)
        self.assertTemplateUsed(response, template_name="account/account_deletion.html")
        self.assertEqual(response.context["user"], self.user)

        response = self.client.post(reverse("account-deletion"))
        self.assertRedirects(response, reverse("homepage"))
        with self.assertRaises(User.DoesNotExist):
            User.objects.get(id=self.user.id)
        self.assertEqual(len(mail.outbox), 1)

        mail.outbox = []
        self.user = None
        self.login_user()
        with patch("django.core.mail.EmailMultiAlternatives.send") as mock:
            mock.side_effect = SMTPException()
            response = self.client.post(reverse("account-deletion"))
            self.assertRedirects(response, reverse("homepage"))
            messages = [str(message) for message in get_messages(response.wsgi_request)]
            self.assertIn(
                "Email confirmation of deletion could not be sent.",
                messages,
            )
            self.assertEqual(len(mail.outbox), 0)

        mail.outbox = []
        self.user = None
        self.login_user()
        transcription = create_transcription(user=self.user)
        response = self.client.post(reverse("account-deletion"))
        self.assertRedirects(response, reverse("homepage"))
        user = User.objects.get(id=self.user.id)
        transcription = Transcription.objects.get(id=transcription.id)
        self.assertEqual(transcription.user, user)
        self.assertIn("Anonymized", user.username)
        self.assertEqual(user.first_name, "")
        self.assertEqual(user.last_name, "")
        self.assertEqual(user.email, "")
        self.assertFalse(user.has_usable_password())
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_active)
        self.assertEqual(len(mail.outbox), 1)
