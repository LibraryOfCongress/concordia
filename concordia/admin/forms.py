import nh3
from django import forms
from django.core.cache import caches
from tinymce.widgets import TinyMCE

from ..models import (
    Campaign,
    Card,
    Guide,
    Item,
    Project,
    ProjectTopic,
    Topic,
    TranscriptionStatus,
)

FRAGMENT_ALLOWED_TAGS = {
    "a",
    "abbr",
    "acronym",
    "b",
    "blockquote",
    "br",
    "code",
    "em",
    "i",
    "kbd",
    "li",
    "ol",
    "p",
    "span",
    "strong",
    "ul",
}

BLOCK_ALLOWED_TAGS = FRAGMENT_ALLOWED_TAGS | {
    "div",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "section",
}

ALLOWED_ATTRIBUTES = {
    "a": {"class", "id", "href", "title"},
    "abbr": {"title"},
    "acronym": {"title"},
    "div": {"class", "id"},
    "span": {"class", "id"},
    "p": {"class", "id"},
}


class AdminItemImportForm(forms.Form):
    import_url = forms.URLField(
        required=True, label="URL of the item/collection/search page to import"
    )


class AdminProjectBulkImportForm(forms.Form):
    spreadsheet_file = forms.FileField(
        required=True,
        label="Spreadsheet containing the campaigns, projects, and items to import",
    )

    redownload = forms.BooleanField(
        required=False, label="Should existing items be redownloaded?"
    )


class AdminRedownloadImagesForm(forms.Form):
    spreadsheet_file = forms.FileField(
        required=True,
        label="Spreadsheet containing the URLs of assets to re-download",
    )


class SanitizedDescriptionAdminForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = "__all__"

    def clean_description(self):
        return nh3.clean(
            self.cleaned_data["description"],
            tags=BLOCK_ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
        )

    def clean_short_description(self):
        return nh3.clean(
            self.cleaned_data["short_description"],
            tags=FRAGMENT_ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
        )


class TopicAdminForm(SanitizedDescriptionAdminForm):
    class Meta(SanitizedDescriptionAdminForm.Meta):
        model = Topic
        widgets = {
            "description": TinyMCE(),
            "short_description": TinyMCE(),
        }


class CampaignAdminForm(SanitizedDescriptionAdminForm):
    class Meta(SanitizedDescriptionAdminForm.Meta):
        model = Campaign
        widgets = {
            "short_description": TinyMCE(),
            "description": TinyMCE(),
        }
        fields = "__all__"


class ProjectAdminForm(SanitizedDescriptionAdminForm):
    class Meta(SanitizedDescriptionAdminForm.Meta):
        model = Project
        widgets = {
            "description": TinyMCE(),
        }


class ProjectTopicInlineForm(forms.ModelForm):
    url_filter = forms.ChoiceField(
        choices=[("", "-- All Statuses --")] + list(TranscriptionStatus.CHOICES),
        required=False,
    )

    class Meta:
        model = ProjectTopic
        fields = ["topic", "url_filter"]


class ItemAdminForm(forms.ModelForm):
    class Meta:
        model = Item
        widgets = {"description": TinyMCE()}
        fields = "__all__"


class CardAdminForm(forms.ModelForm):
    class Meta:
        model = Card
        widgets = {
            "body_text": TinyMCE(),
        }
        fields = "__all__"


class GuideAdminForm(forms.ModelForm):
    class Meta:
        model = Guide
        widgets = {
            "body": TinyMCE(),
        }
        fields = "__all__"


def get_cache_name_choices():
    # We don't want the default cache to be cleared,
    # since it's meant to contain semi-persistent data
    return [
        (name, f"{name} ({settings['BACKEND']})")
        for name, settings in caches.settings.items()
        if name != "default"
    ]


class ClearCacheForm(forms.Form):
    cache_name = forms.ChoiceField(choices=get_cache_name_choices)


class AssetStatusActionForm(forms.Form):
    """
    Displays a select‐box of actions, plus a hidden _selected_action,
    to be submitted to the changelist, just like admin actions usually are.
    You must pass in `available_actions` when creating the form.

    This form is used to avoid manually constructing this in the template
    It won't actually be used to process the data, which is handled by
    the changelist view, just like actions on the changelist itself
    """

    action = forms.ChoiceField(
        choices=(),
        label="Change status",
        widget=forms.Select(attrs={"class": "vSelectField"}),
    )

    def __init__(self, *args, available_actions, **kwargs):
        """
        available_actions: list [action_name, action_label]
        """
        super().__init__(*args, **kwargs)

        choices = [("", "---------")]

        for action_name, action_label in available_actions:
            choices.append((action_name, action_label))

        self.fields["action"].choices = choices
