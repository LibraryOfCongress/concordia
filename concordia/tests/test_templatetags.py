from django.http import QueryDict
from django.template import Context, Template
from django.templatetags.static import static
from django.test import TestCase, override_settings
from django.utils.html import escape, format_html

from concordia.models import TranscriptionStatus
from concordia.templatetags.concordia_filtering_tags import transcription_status_filters
from concordia.templatetags.concordia_text_tags import reprchar
from concordia.templatetags.custom_math import multiply
from concordia.templatetags.reject_filter import reject
from concordia.templatetags.truncation import (
    WordBreakTruncator,
    truncatechars_on_word_break,
)
from concordia.templatetags.visualization import concordia_visualization


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

    def test_reprchar_variants(self):
        cases = [
            ("A", "A"),
            ("\n", "\\n"),
            ("\x00", "\\x00"),
            ("\u200b", "\\u200b"),
            ("\\", "\\\\"),
        ]
        for ch, expected in cases:
            self.assertEqual(reprchar(ch), expected)


class RejectFilterTests(TestCase):
    def test_returns_input_when_falsy(self):
        self.assertEqual(reject("", "x"), "")
        self.assertEqual(reject([], "x"), [])
        self.assertIsNone(reject(None, "x"))
        self.assertEqual(reject((), "x"), ())

    def test_string_single_reject(self):
        self.assertEqual(
            reject("error warn marked-safe", "marked-safe"),
            "error warn",
        )

    def test_string_multiple_rejects(self):
        self.assertEqual(
            reject("error warn marked-safe", "marked-safe,warn"),
            "error",
        )

    def test_string_no_match(self):
        self.assertEqual(reject("one two", "three"), "one two")

    def test_string_empty_args(self):
        self.assertEqual(reject("one two", ""), "one two")

    def test_string_whitespace_split_and_join(self):
        self.assertEqual(reject("a   b\tc", "b"), "a c")

    def test_string_case_sensitivity(self):
        self.assertEqual(reject("A a", "a"), "A")

    def test_iterable_list(self):
        self.assertEqual(
            reject(["ok", "deprecated", "x", "hidden"], "deprecated,hidden"),
            ["ok", "x"],
        )

    def test_iterable_tuple_and_duplicates(self):
        self.assertEqual(reject(("a", "b", "c", "b"), "b"), ["a", "c"])

    def test_iterable_no_match(self):
        self.assertEqual(reject(["one", "two"], "three"), ["one", "two"])

    def test_iterable_empty_args(self):
        self.assertEqual(reject(["one", "two"], ""), ["one", "two"])


@override_settings(
    STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage"
)
class VisualizationTagsTests(TestCase):
    def test_without_attrs_renders_section_and_script(self):
        # No attributes: should render a plain <section> and matching <script>
        result = concordia_visualization("daily-activity")
        expected_section = (
            '<div class="visualization-container"><section>'
            '<canvas id="daily-activity"></canvas></section></div>'
        )
        self.assertHTMLEqual(result, expected_section)

    def test_with_attrs_and_escaping(self):
        # Attributes that include characters needing HTML escaping
        attrs = {"class": "test-class", "style": "width:100%;", "data-info": "<alert>"}
        result = concordia_visualization("chart1", **attrs)

        escaped_value = escape("<alert>")
        expected_section = (
            f'<div class="visualization-container test-class" '
            f'style="width:100%;" data-info="{escaped_value}">'
            f"<section >"
            f'<canvas id="chart1"></canvas>'
            f"</section>"
            f"</div>"
        )
        self.assertHTMLEqual(result, expected_section)

    def test_name_escaping_in_id_and_script_src(self):
        # Name contains characters needing HTML escaping
        name = 'x"><script>alert(1)</script>'
        script_src = static(f"js/visualizations/{name}.js")
        script_html = format_html(
            '<script type="module" src="{}"></script>', script_src
        )
        result = concordia_visualization(name) + script_html

        # The id attribute must have the name escaped
        escaped_id = escape(name)
        self.assertIn(f'id="{escaped_id}"', result)

        # The script src must also be escaped
        raw_src = static(f"js/visualizations/{name}.js")
        escaped_src = escape(raw_src)
        self.assertIn(f'src="{escaped_src}"', result)
