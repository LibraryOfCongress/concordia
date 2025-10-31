from types import SimpleNamespace

from django.test import TestCase

from concordia.logging import get_logging_user_id
from concordia.utils import get_anonymous_user

from .utils import CreateTestUsers


class LoggingTests(CreateTestUsers, TestCase):
    def test_get_logging_user_id_authenticated_user(self):
        user = self.create_test_user()
        self.assertEqual(get_logging_user_id(user), str(user.id))

    def test_get_logging_user_id_anonymous_user(self):
        anon = get_anonymous_user()
        self.assertEqual(get_logging_user_id(anon), "anonymous")

    def test_get_logging_user_id_missing_auth_attribute(self):
        mock_user = object()
        self.assertEqual(get_logging_user_id(mock_user), "anonymous")

    def test_get_logging_user_id_authenticated_no_id(self):
        user = SimpleNamespace(is_authenticated=True, username="someuser")
        self.assertEqual(get_logging_user_id(user), "anonymous")
