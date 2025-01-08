from django.test import RequestFactory, TestCase

from concordia.authentication_backends import EmailOrUsernameModelBackend

from .utils import CreateTestUsers


class AuthenticationBackendTests(TestCase, CreateTestUsers):
    def test_EmailOrUsernameModelBackend(self):
        backend = EmailOrUsernameModelBackend()
        request_factory = RequestFactory()
        test_user = self.create_user("tester")
        request = request_factory.get("/")

        # Fail to authenticate with no information
        user = backend.authenticate(request)
        self.assertEqual(user, None)

        # Fail to authenticate with no password, using username
        user = backend.authenticate(request, test_user.username)
        self.assertEqual(user, None)

        # Authenticate with correct password, using username
        user = backend.authenticate(request, test_user.username, test_user._password)
        self.assertEqual(user, test_user)

        # Fail to authenticate with no password, using email
        user = backend.authenticate(request, test_user.email)
        self.assertEqual(user, None)

        # Authenticate with correct password, using email
        user = backend.authenticate(request, test_user.email, test_user._password)
        self.assertEqual(user, test_user)

        # Fail to authenticate with incorrect password, using username
        user = backend.authenticate(request, test_user.username, "bad-password")
        self.assertEqual(user, None)

        # Fail to authenticate with incorrect password, using email
        user = backend.authenticate(request, test_user.email, "bad-password")
        self.assertEqual(user, None)

        # Same tests, with user with a username
        # the same as the first user's email address
        test_user2 = self.create_user(test_user.email)

        # Fail to authenticate with no password, using username
        user = backend.authenticate(request, test_user2.username)
        self.assertEqual(user, None)

        # Authenticate with correct password, using username
        user = backend.authenticate(request, test_user2.username, test_user2._password)
        self.assertEqual(user, test_user2)

        # Fail to authenticate with no password, using email
        user = backend.authenticate(request, test_user2.email)
        self.assertEqual(user, None)

        # Authenticate with correct password, using email
        user = backend.authenticate(request, test_user2.email, test_user2._password)
        self.assertEqual(user, test_user2)

        # Fail to authenticate with incorrect password, using username
        user = backend.authenticate(request, test_user2.username, "bad-password")
        self.assertEqual(user, None)

        # Fail to authenticate with incorrect password, using email
        user = backend.authenticate(request, test_user2.email, "bad-password")
        self.assertEqual(user, None)
