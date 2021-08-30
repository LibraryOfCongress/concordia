import bleach
from django import forms

FRAGMENT_ALLOWED_TAGS = bleach.sanitizer.ALLOWED_TAGS + ["br", "kbd", "span"]

BLOCK_ALLOWED_TAGS = FRAGMENT_ALLOWED_TAGS + [
    "div",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "p",
    "section",
]

ALLOWED_ATTRIBUTES = {
    **bleach.sanitizer.ALLOWED_ATTRIBUTES,
    "a": ["class", "id", "href", "title"],
    "div": ["class", "id"],
    "span": ["class", "id"],
    "p": ["class", "id"],
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


class AdminRedownloadImagesForm(forms.Form):
    spreadsheet_file = forms.FileField(
        required=True,
        label="Spreadsheet containing the URLs of assets to re-download",
    )


class AdminProcessBagitForm(forms.Form):
    zip_file = forms.FileField(
        required=True,
        label="zip file containing Bagit Structure",
    )


class BleachedDescriptionAdminForm(forms.ModelForm):
    def clean_description(self):
        return bleach.clean(
            self.cleaned_data["description"],
            tags=BLOCK_ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
        )

    def clean_short_description(self):
        return bleach.clean(
            self.cleaned_data["short_description"],
            tags=FRAGMENT_ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
        )


class SimpleContentBlockAdminForm(forms.ModelForm):
    def clean_body(self):
        return bleach.clean(
            self.cleaned_data["body"],
            tags=BLOCK_ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
        )
