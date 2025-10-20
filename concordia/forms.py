from logging import getLogger

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm,
    SetPasswordForm,
    UsernameField,
)
from django_registration.backends.activation.views import RegistrationView
from django_registration.forms import RegistrationForm
from django_registration.signals import user_activated

from .turnstile.fields import TurnstileField

User = get_user_model()


logger = getLogger(__name__)


class AllowInactivePasswordResetForm(PasswordResetForm):
    def get_users(self, email):
        # Allow inactive users to reset their passwords and confirm their email
        # account in one step.
        all_users = User._default_manager.filter(
            **{"%s__iexact" % User.get_email_field_name(): email}
        )
        return (u for u in all_users if u.has_usable_password())


class ActivateAndSetPasswordForm(SetPasswordForm):
    # A successful password reset means the user
    # has confirmed their email address, so
    # set is_active to True.
    def save(self, commit=True):
        if not self.user.is_active:
            logger.info("Activated user %s due to password reset", self.user.username)
            self.user.is_active = True
            # send user_activation signal so that the user will
            # receive a welcome email
            user_activated.send(sender=self.__class__, user=self.user, request=None)
        return super().save()


class UserRegistrationForm(RegistrationForm):
    newsletterOptIn = forms.BooleanField(
        label="Newsletter",
        initial=True,
        required=False,
        help_text=(
            "Email me 2-3 times a month about campaign updates, upcoming "
            "events, and new features."
        ),
    )

    class Meta(RegistrationForm.Meta):
        help_texts = {
            "username": (
                "Can only contain letters, numbers, and any of these symbols:"
                " <kbd>@</kbd>, <kbd>.</kbd>, <kbd>+</kbd>, <kbd>-</kbd>,"
                " or <kbd>_</kbd>."
                " 150 characters or fewer."
            )
        }


class UserLoginForm(AuthenticationForm):
    username = UsernameField(
        label="Username or email address",
        widget=forms.TextInput(attrs={"autofocus": True}),
    )

    def confirm_login_allowed(self, user):
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
    first_name = forms.CharField(label="", required=False)
    last_name = forms.CharField(label="", required=False)


class UserProfileForm(forms.Form):
    email = forms.EmailField(label="", required=True)

    def __init__(self, *, request, **kwargs):
        self.request = request
        super().__init__(**kwargs)

    def clean_email(self):
        data = self.cleaned_data["email"]
        # Previously, this code only checked against other users, but it
        # is also an error if a user tries to change their email to the one
        # they're already using--we don't want to initiate the email
        # confirmation process when the user isn't actually checking their email.
        if User.objects.filter(email__iexact=data).exists():
            raise forms.ValidationError("That email address is not available")
        return data


class AccountDeletionForm(forms.Form):
    def __init__(self, *, request, **kwargs):
        self.request = request
        super().__init__(**kwargs)


class TurnstileForm(forms.Form):
    turnstile = TurnstileField()
