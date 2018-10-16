from logging import getLogger

from captcha.fields import CaptchaField
from django import forms
from django.contrib.auth import get_user_model
from django_registration.forms import RegistrationForm

from .models import TranscriptionStatus

User = get_user_model()
logger = getLogger(__name__)


class UserRegistrationForm(RegistrationForm):
    newsletterOptIn = forms.BooleanField(
        label="Newsletter",
        required=False,
        help_text="Email me about campaign updates, upcoming events, and new features.",
    )


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
    referrer = forms.CharField(label="Referring Page", widget=forms.HiddenInput())

    email = forms.EmailField(label="Your email:", required=True)
    subject = forms.CharField(label="Subject:", required=False)


    link = forms.URLField(
        label="Have a specific page you need help with? Add the link below:", required=False
    )

    story = forms.CharField(
        label="Let us know how we can help:", required=True, widget=forms.Textarea
    )


class CaptchaEmbedForm(forms.Form):
    captcha = CaptchaField()


class AssetFilteringForm(forms.Form):
    transcription_status = forms.ChoiceField(
        choices=TranscriptionStatus.CHOICES,
        required=False,
        label="Image Status",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    def __init__(self, status_counts, *args, **kwargs):
        super().__init__(*args, **kwargs)

        asset_statuses = {
            status: "%s (%d)" % (TranscriptionStatus.CHOICE_MAP[status], count)
            for status, count in status_counts.items()
        }

        filtered_choices = [("", f"All Images ({sum(status_counts.values())})")]
        for val, label in self.fields["transcription_status"].choices:
            if val in asset_statuses:
                filtered_choices.append((val, asset_statuses[val]))

        self.fields["transcription_status"].choices = filtered_choices


class AdminItemImportForm(forms.Form):
    import_url = forms.URLField(
        required=True, label="URL of the item/collection/search page to import"
    )


class AdminProjectBulkImportForm(forms.Form):
    spreadsheet_file = forms.FileField(
        required=True,
        label="Spreadsheet containing the campaigns, projects, and items to import",
    )
