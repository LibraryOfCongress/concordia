from django.test import TestCase, override_settings

from concordia.admin.forms import SanitizedDescriptionAdminForm, get_cache_name_choices
from concordia.models import Campaign


class SanitizedDescriptionAdminFormTests(TestCase):
    def test_clean(self):
        short_description = "<strong>Arm</strong>"
        data = {
            "slug": "test",
            "title": "Test",
            "status": Campaign.Status.ACTIVE,
            "ordering": 0,
            "short_description": short_description,
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
