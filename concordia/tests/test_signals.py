from unittest import mock

from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_logged_in
from django.core import mail
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django_registration.signals import user_activated, user_registered

from .utils import CreateTestUsers, create_asset


class TestSignalHandlers(CreateTestUsers, TestCase):
    def setUp(self):
        self.user = self.create_test_user()
        self.asset = create_asset()
        self.request_factory = RequestFactory()

    def test_clear_reservation_token(self):
        self.login_user()
        response = self.client.get(reverse("redirect-to-next-transcribable-asset"))
        self.assertIsNotNone(self.client.session.get("reservation_token"))
        user_logged_in.send(
            sender=self.__class__, user=self.user, request=response.wsgi_request
        )
        self.assertIsNone(self.client.session.get("reservation_token"))

    def test_user_successfully_activated(self):
        with mock.patch("concordia.signals.handlers.flag_enabled") as flag_mock:
            flag_mock.return_value = True
            response = self.client.get("/")
            request = response.wsgi_request
            user_activated.send(sender=self.__class__, user=self.user, request=request)
            self.assertTrue(request.user.is_authenticated)
            self.assertEqual(len(mail.outbox), 1)

    def test_add_user_to_newsletter(self):
        self.login_user()
        response = self.client.post("/")
        user_registered.send(
            sender=self.__class__, user=self.user, request=response.wsgi_request
        )
        self.assertNotIn(
            self.user,
            Group.objects.get(name=settings.NEWSLETTER_GROUP_NAME).user_set.all(),
        )

        response = self.client.post("/", data={"newsletterOptIn": True})
        user_registered.send(
            sender=self.__class__, user=self.user, request=response.wsgi_request
        )
        self.assertIn(
            self.user,
            Group.objects.get(name=settings.NEWSLETTER_GROUP_NAME).user_set.all(),
        )
