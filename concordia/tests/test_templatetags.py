from django.http import QueryDict
from django.template import Context, Template
from django.test import TestCase

from concordia.models import TranscriptionStatus
from concordia.templatetags.concordia_filtering_tags import transcription_status_filters
from concordia.templatetags.custom_math import multiply
from concordia.templatetags.truncation import (
    WordBreakTruncator,
    truncatechars_on_word_break,
)


class TestTemplateTags(TestCase):
    def test_truncatechars_on_word_break(self):
        test_string = "Lorem ipsum \u0317 dolor sit amet, consectetur adipiscing elit"

        self.assertEqual(truncatechars_on_word_break(test_string, 0), "[…]")
        self.assertEqual(truncatechars_on_word_break(test_string, 1), "[…]")
        self.assertEqual(truncatechars_on_word_break(test_string, 10), "Lorem[…]")
        self.assertEqual(
            truncatechars_on_word_break(test_string, 30),
            "Lorem ipsum \u0317 dolor sit[…]",
        )
        self.assertEqual(truncatechars_on_word_break(test_string, 1000), test_string)
        self.assertEqual(
            truncatechars_on_word_break(test_string, "badvalue"), test_string
        )

        self.assertEqual(
            WordBreakTruncator(test_string).word_break(30, "[\u0317]"),
            "Lorem ipsum \u0317 dolor sit[\u0317]",
        )

    def test_multiply(self):
        self.assertEqual(multiply(5, 5), 5 * 5)
        self.assertEqual(multiply(0, 5), 0 * 5)
        self.assertEqual(multiply(1, 2), 1 * 2)

    def test_transcription_status_filters(self):
        status_counts = []
        for choice in TranscriptionStatus.CHOICES:
            status_counts.append((choice, 0, 1))

        transcription_status_filters(status_counts, "")
        transcription_status_filters(status_counts, "", reversed_order=True)
        transcription_status_filters(status_counts, TranscriptionStatus.CHOICES[0][0])

    def test_qs_alter(self):
        base_template = "{% load concordia_querystring %}"

        out = Template(
            base_template + "{% qs_alter 'bar=baz&baz=taz' foo='bar' %}"
        ).render(Context())
        self.assertEqual(out, "bar=baz&amp;baz=taz&amp;foo=bar")

        data = QueryDict("bar=baz&baz=taz&bar=foo")
        out = Template(base_template + "{% qs_alter data foo='bar' %}").render(
            Context({"data": data})
        )
        self.assertEqual(out, "bar=baz&amp;bar=foo&amp;baz=taz&amp;foo=bar")

        out = Template(base_template + "{% qs_alter data delete:bar %}").render(
            Context({"data": data})
        )
        self.assertEqual(out, "baz=taz")

        out = Template(base_template + "{% qs_alter data delete:taz %}").render(
            Context({"data": data})
        )
        self.assertEqual(out, "bar=baz&amp;bar=foo&amp;baz=taz")

        out = Template(
            base_template + "{% qs_alter data delete_value:\"bar\",'foo' %}"
        ).render(Context({"data": data}))
        self.assertEqual(out, "bar=baz&amp;baz=taz")

        out = Template(
            base_template + "{% qs_alter data delete_value:'bar','taz' %}"
        ).render(Context({"data": data}))
        self.assertEqual(out, "bar=baz&amp;bar=foo&amp;baz=taz")

        out = Template(
            base_template + "{% qs_alter data foo='bar' as new_data %}" "{{ new_data }}"
        ).render(Context({"data": data}))
        self.assertEqual(out, "bar=baz&amp;bar=foo&amp;baz=taz&amp;foo=bar")

        # Test add_if_missing when the key already exists (should not overwrite)
        out = Template(
            base_template + "{% qs_alter data add_if_missing:bar='newvalue' %}"
        ).render(Context({"data": data}))
        self.assertEqual(out, "bar=baz&amp;bar=foo&amp;baz=taz")
