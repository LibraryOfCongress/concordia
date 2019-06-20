from django.core.exceptions import ValidationError
from django.template import Context, Template
from django.test import TestCase

from concordia.models import SimpleContentBlock


class TestSimpleContentBlocks(TestCase):
    def test_block_creation(self):
        b = SimpleContentBlock()
        self.assertRaises(ValidationError, b.full_clean)

        b = SimpleContentBlock(label="test")
        self.assertRaises(ValidationError, b.full_clean)

        b = SimpleContentBlock(body="test")
        self.assertRaises(ValidationError, b.full_clean)

        b = SimpleContentBlock(label="test", body="test")
        b.save()

    def test_block_string_representation(self):
        b = SimpleContentBlock(label="foo", body="bar")
        self.assertEqual(str(b), "SimpleContentBlock: foo")


class TestSimpleContentBlockTags(TestCase):
    def test_basic_block(self):
        SimpleContentBlock.objects.create(label="boring-block", body="Boring Block")
        context = Context()
        template = Template(
            """
            {% load concordia_simple_content_blocks %}
            {% simple_content_block "boring-block" %}
            """
        )

        rendered = template.render(context)

        self.assertIn("Boring Block", rendered)

    def test_missing_block(self):
        context = Context()
        template = Template(
            """
            {% load concordia_simple_content_blocks %}
            {% simple_content_block "no-such-block" %}
            """
        )

        rendered = template.render(context)

        self.assertEqual(rendered.strip(), "")

    def test_block_with_template_markup(self):
        SimpleContentBlock.objects.create(
            label="block-with-template-markup",
            body="""<a href="{% url 'homepage' %}"></a>""",
        )
        context = Context()
        template = Template(
            """
            {% load concordia_simple_content_blocks %}
            {% simple_content_block "block-with-template-markup" %}
            """
        )

        rendered = template.render(context)

        self.assertIn('<a href="/"></a>', rendered)
