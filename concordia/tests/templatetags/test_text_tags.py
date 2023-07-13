from django.test import TestCase

from concordia.templatetags.concordia_text_tags import truncate_left


class TextTagsTestCase(TestCase):
    def test_truncate_left(self):
        self.assertEqual(
            truncate_left("General Correspondence: Q-Z"), "...Correspondence: Q-Z"
        )
