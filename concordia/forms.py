from logging import getLogger

from django import forms
from django.contrib.auth import get_user_model
from django_registration.forms import RegistrationForm

User = get_user_model()
logger = getLogger(__name__)


class UserRegistrationForm(RegistrationForm):
    newsletterOptIn = forms.BooleanField(
        label="Newsletter",
        required=False,
        help_text="Email me about campaign updates, upcoming events, and new features.",
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


class UserProfileForm(forms.Form):
    email = forms.CharField(
        label="Email address", required=True, widget=forms.EmailInput()
    )

    def __init__(self, *, request, **kwargs):
        self.request = request
        return super().__init__(**kwargs)

    def clean_email(self):
        data = self.cleaned_data["email"]
        if (
            User.objects.exclude(pk=self.request.user.pk)
            .filter(email__iexact=data)
            .exists()
        ):
            raise forms.ValidationError("That email address is not available")
        return data


class ContactUsForm(forms.Form):
    referrer = forms.CharField(
        label="Referring Page", widget=forms.HiddenInput(), required=False
    )

    email = forms.EmailField(label="Your email:", required=True)
    subject = forms.CharField(label="Subject:", required=True)

    link = forms.URLField(
        label="Have a specific page you need help with? Add the link below:",
        required=False,
    )

    story = forms.CharField(
        label="Let us know how we can help:", required=True, widget=forms.Textarea
    )


class AdminItemImportForm(forms.Form):
    import_url = forms.URLField(
        required=True, label="URL of the item/collection/search page to import"
    )


class AdminProjectBulkImportForm(forms.Form):
    spreadsheet_file = forms.FileField(
        required=True,
        label="Spreadsheet containing the campaigns, projects, and items to import",
    )
