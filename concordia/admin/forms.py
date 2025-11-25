import nh3
from django import forms
from django.core.cache import caches
from tinymce.widgets import TinyMCE

from ..models import (
    Campaign,
    Card,
    Guide,
    Item,
    KeyMetricsReport,
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
    """
    Admin form for importing items into a project from a URL.

    Provides a single `import_url` field pointing to an item, collection or
    search page to import from.
    """

    import_url = forms.URLField(
        required=True, label="URL of the item/collection/search page to import"
    )


class AdminProjectBulkImportForm(forms.Form):
    """
    Admin form for bulk importing campaigns, projects and items.

    Accepts a spreadsheet file describing the content to import and an
    optional `redownload` flag that controls whether existing items should
    be fetched again.
    """

    spreadsheet_file = forms.FileField(
        required=True,
        label="Spreadsheet containing the campaigns, projects, and items to import",
    )

    redownload = forms.BooleanField(
        required=False, label="Should existing items be redownloaded?"
    )


class AdminAssetsBulkChangeStatusForm(forms.Form):
    """
    Admin form for changing status of assets across multiple items in bulk
    via CSV upload.
    """

    spreadsheet_file = forms.FileField(
        required=True,
        label="Spreadsheet containing the items to change",
    )


class SanitizedDescriptionAdminForm(forms.ModelForm):
    """
    Base admin form that sanitizes HTML description fields.

    Uses `nh3` to strip disallowed tags and attributes from `description`
    and `short_description` fields while keeping a limited set of inline
    and block-level markup.
    """

    class Meta:
        model = Campaign
        fields = "__all__"

    def clean_description(self) -> str:
        """
        Clean the `description` field using the block-level sanitizer.

        Returns:
            str: Sanitized HTML content for `description`.
        """
        return nh3.clean(
            self.cleaned_data["description"],
            tags=BLOCK_ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
        )

    def clean_short_description(self) -> str:
        """
        Clean the `short_description` field using the fragment sanitizer.

        Returns:
            str: Sanitized HTML content for `short_description`.
        """
        return nh3.clean(
            self.cleaned_data["short_description"],
            tags=FRAGMENT_ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
        )


class TopicAdminForm(SanitizedDescriptionAdminForm):
    """
    Admin form for topics with sanitized rich-text descriptions.
    """

    class Meta(SanitizedDescriptionAdminForm.Meta):
        model = Topic
        widgets = {
            "description": TinyMCE(),
            "short_description": TinyMCE(),
        }


class CampaignAdminForm(SanitizedDescriptionAdminForm):
    """
    Admin form for campaigns with sanitized rich-text descriptions.
    """

    class Meta(SanitizedDescriptionAdminForm.Meta):
        model = Campaign
        widgets = {
            "short_description": TinyMCE(),
            "description": TinyMCE(),
        }
        fields = "__all__"


class ProjectAdminForm(SanitizedDescriptionAdminForm):
    """
    Admin form for projects with sanitized rich-text descriptions.
    """

    class Meta(SanitizedDescriptionAdminForm.Meta):
        model = Project
        widgets = {
            "description": TinyMCE(),
        }


class ProjectTopicInlineForm(forms.ModelForm):
    """
    Admin inline form that links `Project` and `Topic` with a URL filter.

    Adds a `url_filter` choice field that maps to `TranscriptionStatus`
    values and controls which asset statuses are shown in topic URLs.
    """

    url_filter = forms.ChoiceField(
        choices=[("", "-- All Statuses --")] + list(TranscriptionStatus.CHOICES),
        required=False,
    )

    class Meta:
        model = ProjectTopic
        fields = ["topic", "url_filter"]


class ItemAdminForm(forms.ModelForm):
    """
    Admin form for items with a rich-text `description` field.
    """

    class Meta:
        model = Item
        widgets = {"description": TinyMCE()}
        fields = "__all__"


class CardAdminForm(forms.ModelForm):
    """
    Admin form for tutorial cards with a rich-text `body_text` field.
    """

    class Meta:
        model = Card
        widgets = {
            "body_text": TinyMCE(),
        }
        fields = "__all__"


class GuideAdminForm(forms.ModelForm):
    """
    Admin form for guides with a rich-text `body` field.
    """

    class Meta:
        model = Guide
        widgets = {
            "body": TinyMCE(),
        }
        fields = "__all__"


def get_cache_name_choices() -> list[tuple[str, str]]:
    """
    Build choices for the cache-clearing admin form.

    Skips the `default` cache, since it holds semi-persistent data that
    should not be cleared through this form.

    Returns:
        list[tuple[str, str]]: `(cache_name, label)` pairs for non-default
            cache aliases.
    """
    # We don't want the default cache to be cleared,
    # since it's meant to contain semi-persistent data
    return [
        (name, f"{name} ({settings['BACKEND']})")
        for name, settings in caches.settings.items()
        if name != "default"
    ]


class ClearCacheForm(forms.Form):
    """
    Admin form for clearing selected Django caches.

    Presents a dropdown of non-default cache aliases built from
    `get_cache_name_choices()`.
    """

    cache_name = forms.ChoiceField(choices=get_cache_name_choices)


class AssetStatusActionForm(forms.Form):
    """
    Admin form used to select an asset status action.

    Renders a select box of available actions plus the hidden
    `_selected_action` field that the changelist expects. You must pass
    `available_actions` when creating the form.

    This form only builds the choice list. The admin changelist view still
    handles processing and execution of the selected action, just like
    standard admin actions.
    """

    action = forms.ChoiceField(
        choices=(),
        label="Change status",
        widget=forms.Select(attrs={"class": "vSelectField"}),
    )

    def __init__(
        self,
        *args,
        available_actions: list[tuple[str, str]],
        **kwargs,
    ) -> None:
        """
        Initialize the form with a list of available admin actions.

        Args:
            available_actions (list[tuple[str, str]]): Pairs of action name
                and human-readable label for each action that should appear
                in the dropdown.
        """
        super().__init__(*args, **kwargs)

        choices: list[tuple[str, str]] = [("", "---------")]

        for action_name, action_label in available_actions:
            choices.append((action_name, action_label))

        self.fields["action"].choices = choices


class KeyMetricsReportAdminForm(forms.ModelForm):
    """
    Admin form for `KeyMetricsReport` objects.

    Keeps manual and calculated metric fields editable while period
    metadata remains read-only through the `KeyMetricsReportAdmin`.
    """

    class Meta:
        model = KeyMetricsReport
        fields = "__all__"
        help_texts = {
            # Manual fields
            "crowd_emails_and_libanswers_sent": (
                "Optional. Leave blank if not known. "
                "Blank values are not included in quarterly or fiscal-year "
                "totals."
            ),
            "crowd_visits": (
                "Optional. Leave blank if not known. "
                "Blank values are not included in quarterly or fiscal-year "
                "totals."
            ),
            "crowd_page_views": (
                "Optional. Leave blank if not known. "
                "Blank values are not included in quarterly or fiscal-year "
                "totals."
            ),
            "crowd_unique_visitors": (
                "Optional. Leave blank if not known. "
                "Blank values are not included in quarterly or fiscal-year "
                "totals."
            ),
            "avg_visit_seconds": (
                "Optional average visit length in seconds. "
                "If blank, no average is used for quarterly or fiscal-year "
                "rollups."
            ),
            "transcriptions_added_to_loc_gov": (
                "Optional. Leave blank if not known. "
                "Blank values are not included in quarterly or fiscal-year "
                "totals."
            ),
            "datasets_added_to_loc_gov": (
                "Optional. Leave blank if not known. "
                "Blank values are not included in quarterly or fiscal-year "
                "totals."
            ),
            # Calculated fields (still editable)
            "assets_published": (
                "Usually calculated from Site Reports. "
                "If you edit this, it may be overwritten when reports are "
                "rebuilt."
            ),
            "assets_started": (
                "Usually calculated from Site Reports. "
                "If you edit this, it may be overwritten when reports are "
                "rebuilt."
            ),
            "assets_completed": (
                "Usually calculated from Site Reports. "
                "If you edit this, it may be overwritten when reports are "
                "rebuilt."
            ),
            "users_activated": (
                "Usually calculated from Site Reports. "
                "If you edit this, it may be overwritten when reports are "
                "rebuilt."
            ),
            "anonymous_transcriptions": (
                "Usually calculated from Site Reports. "
                "If you edit this, it may be overwritten when reports are "
                "rebuilt."
            ),
            "transcriptions_saved": (
                "Usually calculated from Site Reports. "
                "If you edit this, it may be overwritten when reports are "
                "rebuilt."
            ),
            "tag_uses": (
                "Usually calculated from Site Reports. "
                "If you edit this, it may be overwritten when reports are "
                "rebuilt."
            ),
        }
