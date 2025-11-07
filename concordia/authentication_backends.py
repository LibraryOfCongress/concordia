from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Q
from django.http import HttpRequest


class EmailOrUsernameModelBackend(ModelBackend):
    """
    Authentication backend that accepts either username or email.

    Behavior:
      * Looks up users by ``USERNAME_FIELD`` or case-insensitive ``email``.
      * If multiple accounts match (e.g., same email in different fields),
        iterates through matches and returns the first with a valid password.
      * When no user matches, runs the hasher once to reduce timing
        differences between existing and non-existing users.

    Usage:
        In ``settings.py``:

            AUTHENTICATION_BACKENDS = [
                "concordia.authentication_backends.EmailOrUsernameModelBackend",
                "django.contrib.auth.backends.ModelBackend",
            ]

    Security notes:
      * The fallback hash on a miss helps mitigate user enumeration via
        timing side channels.
    """

    def authenticate(
        self,
        request: HttpRequest | None,
        username: str | None = None,
        password: str | None = None,
        **kwargs: Any,
    ) -> AbstractBaseUser | None:
        """
        Authenticate with either a username or an email address.

        Args:
            request:
                The current HTTP request or ``None`` (older Django may pass
                ``None``).
            username:
                The credential provided by the client. May be a username or an
                email address. If ``None``, the method will read the
                ``USERNAME_FIELD`` from ``kwargs``.
            password:
                The plaintext password to validate.

        Returns:
            The authenticated user instance, or ``None`` if authentication
            fails.
        """
        # n.b. Django <2.1 does not pass the `request`
        user_model = get_user_model()

        if username is None:
            username = kwargs.get(user_model.USERNAME_FIELD)

        # The `username` field is allowed to contain `@` characters so
        # technically a given email address could be present in either field,
        # possibly even for different users, so we'll query for all matching
        # records and test each one.
        users = user_model._default_manager.filter(
            Q(**{user_model.USERNAME_FIELD: username}) | Q(email__iexact=username)
        )

        # Test whether any matched user has the provided password:
        for user in users:
            if user.check_password(password):
                return user
        if not users:
            # Run the default password hasher once to reduce the timing
            # difference between an existing and a non-existing user (see
            # https://code.djangoproject.com/ticket/20760)
            user_model().set_password(password)
        return None
