import json
from pathlib import Path
from unittest.mock import mock_open, patch

from django.test import TestCase, override_settings

from concordia.admin.forms import (
    CampaignAdminForm,
    SanitizedDescriptionAdminForm,
    TinyMCEMediaMixin,
    TopicAdminForm,
    get_cache_name_choices,
)
from concordia.models import Campaign


class SanitizedDescriptionAdminFormTests(TestCase):
    def test_clean(self):
        short_description = "<p>Arm</p>"
        data = {
            "slug": "test",
            "title": "Test",
            "status": Campaign.Status.ACTIVE,
            "ordering": 0,
            "short_description": "<div>%s</<div>" % short_description,
            "description": "<script src=example.com/evil.js></script>",
        }
        data["description"] += "<strong>Arm</strong>"
        form = SanitizedDescriptionAdminForm(data)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.clean_short_description(), short_description)
        self.assertEqual(form.clean_description(), "<strong>Arm</strong>")


class ClearCacheFormTests(TestCase):
    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.dummy.DummyCache",
            },
            "view_cache": {
                "BACKEND": "django.core.cache.backends.dummy.DummyCache",
            },
        }
    )
    def test_cache_name_choices(self):
        choices = get_cache_name_choices()
        choice_names = [name for name, description in choices]
        self.assertNotIn("default", choice_names)
        self.assertIn("view_cache", choice_names)


class TinyMCEMediaMixinTests(TestCase):
    def test_media_returns_fallback_script_when_manifest_missing(self) -> None:
        """
        Verify that when the manifest file does not exist, the media property
        falls back to the uncompiled source asset path in a type="module" script tag.
        """
        mixin = TinyMCEMediaMixin()
        with patch.object(Path, "is_file", return_value=False):
            media = mixin.media
            rendered_html = str(media)
            self.assertIn(
                '<script type="module" '
                'src="/static/js/src/tinymce-picker.js"></script>',
                rendered_html,
            )

    def test_media_resolves_hashed_path_from_manifest(self) -> None:
        """
        Verify that when manifest.json is present, media parses the manifest key
        and renders the compiled, hashed bundle URL within an ES Module script tag.
        """
        manifest_data = {
            "./concordia/static/js/src/tinymce-picker.js": {
                "file": "js/tinymce_picker-abc12345.js"
            }
        }
        mock_manifest_json = json.dumps(manifest_data)

        mixin = TinyMCEMediaMixin()
        with (
            patch.object(Path, "is_file", return_value=True),
            patch.object(Path, "open", mock_open(read_data=mock_manifest_json)),
        ):
            media = mixin.media
            rendered_html = str(media)
            self.assertIn(
                '<script type="module" '
                'src="/static/dist/js/tinymce_picker-abc12345.js"></script>',
                rendered_html,
            )

    def test_media_handles_manifest_parse_error_gracefully(self) -> None:
        """
        Verify that if manifest parsing fails, an error is logged via structlog
        and the mixin falls back safely to the source JS path.
        """
        mixin = TinyMCEMediaMixin()
        with (
            patch.object(Path, "is_file", return_value=True),
            patch.object(Path, "open", side_effect=OSError("Disk read error")),
            patch("concordia.admin.forms.logger.error") as mock_log_error,
        ):
            media = mixin.media
            rendered_html = str(media)
            self.assertIn(
                '<script type="module" '
                'src="/static/js/src/tinymce-picker.js"></script>',
                rendered_html,
            )
            mock_log_error.assert_called_once_with(
                "Failed to parse Vite manifest file", error="Disk read error"
            )

    def test_tinymce_forms_include_picker_media(self) -> None:
        """
        Verify that ModelForms incorporating TinyMCEMediaMixin properly include
        the module script tag within form.media.
        """
        form = CampaignAdminForm()
        rendered_media = str(form.media)
        self.assertIn('type="module"', rendered_media)
        self.assertIn("tinymce_picker", rendered_media)

        topic_form = TopicAdminForm()
        rendered_topic_media = str(topic_form.media)
        self.assertIn('type="module"', rendered_topic_media)
        self.assertIn("tinymce_picker", rendered_topic_media)
