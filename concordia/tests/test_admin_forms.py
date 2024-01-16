from django.test import TestCase

from concordia.admin.forms import SanitizedDescriptionAdminForm
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
