from logging import getLogger
from typing import Any, Iterator

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm,
    SetPasswordForm,
    UsernameField,
)
from django.http import HttpRequest
from django_registration.backends.activation.views import RegistrationView
from django_registration.forms import RegistrationForm
from django_registration.signals import user_activated

from .turnstile.fields import TurnstileField

User = get_user_model()

logger = getLogger(__name__)


class AllowInactivePasswordResetForm(PasswordResetForm):
    """
    Password reset form which includes inactive users.

    Behavior:
        Overrides Django's default user lookup so that inactive users with a
        usable password are included, allowing a single reset flow to both
        confirm email and activate the account.
    """

    def get_users(self, email: str) -> Iterator[User]:
        """
        Yield users matching the provided email, including inactive accounts.

        Args:
            email: Case-insensitive email address to search.

        Returns:
            Iterator over users that have a usable password.
        """
        # Allow inactive users to reset their passwords and confirm their email
        # account in one step.
        all_users = User._default_manager.filter(
            **{"%s__iexact" % User.get_email_field_name(): email}
        )
        return (u for u in all_users if u.has_usable_password())


class ActivateAndSetPasswordForm(SetPasswordForm):
    """
    Set-password form which activates the user on successful save.

    Behavior:
        If the associated user is inactive, mark the user active, emit the
        django-registration ``user_activated`` signal to trigger the welcome
        email, then proceed with the normal password save.
    """

    # A successful password reset means the user
    # has confirmed their email address, so
    # set is_active to True.
    def save(self, commit: bool = True) -> User:
        """
        Save the new password and ensure the user is marked active.

        Also emits ``user_activated`` when activation occurs.

        Args:
            commit: Whether to persist changes immediately.

        Returns:
            The updated user instance.
        """
        if not self.user.is_active:
            logger.info("Activated user %s due to password reset", self.user.username)
            self.user.is_active = True
            # send user_activation signal so that the user will
            # receive a welcome email
            user_activated.send(sender=self.__class__, user=self.user, request=None)
        return super().save(commit=commit)


class UserRegistrationForm(RegistrationForm):
    """
    Registration form with newsletter opt-in.

    Adds a boolean field which, when selected, is later used to add the new
    user to the newsletter group during signal handling.
    """

    newsletterOptIn = forms.BooleanField(
        label="Newsletter",
        initial=True,
        required=False,
        help_text=(
            "Email me 2-3 times a month about campaign updates, upcoming "
            "events and new features."
        ),
    )

    class Meta(RegistrationForm.Meta):
        help_texts = {
            "username": (
                "Can only contain letters, numbers and any of these symbols:"
                " <kbd>@</kbd>, <kbd>.</kbd>, <kbd>+</kbd>, <kbd>-</kbd>"
                " or <kbd>_</kbd>. 150 characters or fewer."
            )
        }


class UserLoginForm(AuthenticationForm):
    """
    Login form which resends activation for inactive but valid credentials.

    Behavior:
        If credentials are correct but the user is inactive, resend an
        activation email and raise a validation error with user guidance.
    """

    username = UsernameField(
        label="Username or email address",
        widget=forms.TextInput(attrs={"autofocus": True}),
    )

    def confirm_login_allowed(self, user: Any) -> None:
        """
        Enforce activation: resend activation email and block login if inactive.

        Args:
            user: The authenticated user instance.

        Raises:
            forms.ValidationError: When the user account is inactive.
        """
        inactive_message = (
            "This account has not yet been activated. "
            "An activation email has been sent to the email "
            "address associated with this account. "
            "Please check for this message and click the link "
            "to finish your account registration."
        )

        # If the user provided a correct username and password combination,
        # but has not yet confirmed their email,
        # resend the email activation request and display a custom message.
        if not user.is_active:
            logger.warning("Inactive user tried to log in with valid credentials.")
            view = RegistrationView(request=self.request)
            view.send_activation_email(user)

            raise forms.ValidationError(inactive_message, code="inactive")


class UserNameForm(forms.Form):
    """
    Minimal form for updating a user's first and last name.

    Fields:
        first_name: Optional first name.
        last_name: Optional last name.
    """

    first_name = forms.CharField(label="", required=False)
    last_name = forms.CharField(label="", required=False)


class UserProfileForm(forms.Form):
    """
    Profile form for updating the user's email address.

    Validates that the email is not already in use and, for the current user,
    is not unchanged to avoid unnecessary confirmation flows.
    """

    email = forms.EmailField(label="", required=True)

    def __init__(self, *, request: HttpRequest, **kwargs) -> None:
        """
        Store the request for later use.

        Args:
            request: The current HTTP request.
        """
        self.request = request
        super().__init__(**kwargs)

    def clean_email(self) -> str:
        """
        Validate that the submitted email is available and meaningful.

        Rejects emails already in use by any account and the current user's
        existing email to avoid triggering a redundant confirmation.

        Returns:
            The cleaned email string.

        Raises:
            forms.ValidationError: If the email is not available.
        """
        data = self.cleaned_data["email"]
        # Previously, this code only checked against other users, but it
        # is also an error if a user tries to change their email to the one
        # they're already using--we don't want to initiate the email
        # confirmation process when the user isn't actually checking their email.
        if User.objects.filter(email__iexact=data).exists():
            raise forms.ValidationError("That email address is not available")
        return data


class AccountDeletionForm(forms.Form):
    """
    Trivial form that retains the request for view logic.

    Used where the view needs the request object after validation.
    """

    def __init__(self, *, request: HttpRequest, **kwargs) -> None:
        """
        Store the request for later use.

        Args:
            request: The current HTTP request.
        """
        self.request = request
        super().__init__(**kwargs)


class TurnstileForm(forms.Form):
    """
    Simple form embedding the Cloudflare Turnstile verification field.

    Fields:
        turnstile: A required TurnstileField that validates with the API.
    """

    turnstile = TurnstileField()
