from logging import getLogger

from captcha.fields import CaptchaField
from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Count
from django_registration.forms import RegistrationForm

User = get_user_model()
logger = getLogger(__name__)


class UserRegistrationForm(RegistrationForm):
    newsletterOptIn = forms.BooleanField(
        label="Newsletter",
        required=False,
        help_text="I would like to receive email updates about new campaigns, upcoming events, and feature improvements.",
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

    email = forms.EmailField(label="Your email", required=True)
    subject = forms.CharField(label="Subject", required=False)

    category = forms.CharField(
        label="Category",
        required=True,
        widget=forms.Select(
            choices=(
                ("General", "General"),
                ("Campaign", "Question about campaign"),
                ("Problem", "Something is not working"),
            )
        ),
    )

    link = forms.URLField(
        label="Link to the page you need support with", required=False
    )

    story = forms.CharField(
        label="Why are you contacting us", required=True, widget=forms.Textarea
    )


class CaptchaEmbedForm(forms.Form):
    captcha = CaptchaField()


class AssetFilteringForm(forms.Form):
    pass
    # status = forms.ChoiceField(
    #     choices=Status.CHOICES,
    #     required=False,
    #     label="Image Status",
    #     widget=forms.Select(attrs={"class": "form-control"}),
    # )

    # def __init__(self, asset_qs, *args, **kwargs):
    #     super().__init__(*args, **kwargs)

    #     # We want to get a list of all of the available asset states in this
    #     # item's assets and will return that with the preferred display labels
    #     # including the asset count to be displayed in the filter UI
    #     asset_state_qs = asset_qs.values_list("status")
    #     asset_state_qs = asset_state_qs.annotate(Count("status")).order_by()

    #     asset_states = {
    #         i: "%s (%d)" % (Status.CHOICE_MAP[i], j) for i, j in asset_state_qs
    #     }

    #     filtered_choices = [("", "All Images")]
    #     for val, label in self.fields["status"].choices:
    #         if val in asset_states:
    #             filtered_choices.append((val, asset_states[val]))

    #     self.fields["status"].choices = filtered_choices


class AdminItemImportForm(forms.Form):
    import_url = forms.URLField(
        required=True, label="URL of the item/collection/search page to import"
    )


class AdminProjectBulkImportForm(forms.Form):
    spreadsheet_file = forms.FileField(
        required=True,
        label="Spreadsheet containing the campaigns, projects, and items to import",
    )
