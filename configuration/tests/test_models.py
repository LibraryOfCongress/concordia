import json

from django.test import TestCase

from configuration.models import Configuration


class TestConfiguration(TestCase):
    def test_str(self):
        config = Configuration.objects.create(
            key="test-key", value="Test value", data_type=Configuration.DataType.TEXT
        )
        self.assertEqual(str(config), "test-key")

    def test_text(self):
        config = Configuration.objects.create(
            key="test-key", value="Test value", data_type=Configuration.DataType.TEXT
        )
        self.assertEqual(config.get_value(), "Test value")

        config2 = Configuration.objects.create(
            key="test-key2", value="", data_type=Configuration.DataType.TEXT
        )
        self.assertEqual(config2.get_value(), "")

        config3 = Configuration.objects.create(
            key="test-key3",
            value='{"key" : "value"}',
            data_type=Configuration.DataType.TEXT,
        )
        self.assertEqual(config3.get_value(), '{"key" : "value"}')

    def test_number(self):
        config = Configuration.objects.create(
            key="test-key", value="100", data_type=Configuration.DataType.NUMBER
        )
        self.assertEqual(config.get_value(), 100)

        config2 = Configuration.objects.create(
            key="test-key2", value="100.12", data_type=Configuration.DataType.NUMBER
        )
        self.assertEqual(config2.get_value(), 100.12)

        config3 = Configuration.objects.create(
            key="test-key3", value="Test value", data_type=Configuration.DataType.NUMBER
        )
        self.assertEqual(config3.get_value(), 0)

        config4 = Configuration.objects.create(
            key="test-key4", value="", data_type=Configuration.DataType.NUMBER
        )
        self.assertEqual(config4.get_value(), 0)

    def test_boolean(self):
        config = Configuration.objects.create(
            key="test-key", value="True", data_type=Configuration.DataType.BOOLEAN
        )
        self.assertEqual(config.get_value(), True)

        config2 = Configuration.objects.create(
            key="test-key2", value="true", data_type=Configuration.DataType.BOOLEAN
        )
        self.assertEqual(config2.get_value(), True)

        config3 = Configuration.objects.create(
            key="test-key3", value="TrUe", data_type=Configuration.DataType.BOOLEAN
        )
        self.assertEqual(config3.get_value(), True)

        config4 = Configuration.objects.create(
            key="test-key4", value="", data_type=Configuration.DataType.BOOLEAN
        )
        self.assertEqual(config4.get_value(), False)

        config5 = Configuration.objects.create(
            key="test-key5", value="1", data_type=Configuration.DataType.BOOLEAN
        )
        self.assertEqual(config5.get_value(), False)

        config6 = Configuration.objects.create(
            key="test-key6",
            value="Test value",
            data_type=Configuration.DataType.BOOLEAN,
        )
        self.assertEqual(config6.get_value(), False)

    def test_json(self):
        config = Configuration.objects.create(
            key="test-key", value="true", data_type=Configuration.DataType.JSON
        )
        self.assertEqual(config.get_value(), True)

        config2 = Configuration.objects.create(
            key="test-key2", value="True", data_type=Configuration.DataType.JSON
        )
        self.assertRaises(json.decoder.JSONDecodeError, config2.get_value)

        config3 = Configuration.objects.create(
            key="test-key3",
            value='{"key" : "value"}',
            data_type=Configuration.DataType.JSON,
        )
        self.assertEqual(config3.get_value(), {"key": "value"})

        config4 = Configuration.objects.create(
            key="test-key4", value="", data_type=Configuration.DataType.JSON
        )
        self.assertRaises(json.decoder.JSONDecodeError, config4.get_value)

        config5 = Configuration.objects.create(
            key="test-key5", value="1", data_type=Configuration.DataType.JSON
        )
        self.assertEqual(config5.get_value(), 1)

        config6 = Configuration.objects.create(
            key="test-key6", value="Test value", data_type=Configuration.DataType.JSON
        )
        self.assertRaises(json.decoder.JSONDecodeError, config6.get_value)

    def test_html(self):
        config = Configuration.objects.create(
            key="test-key", value="Test value", data_type=Configuration.DataType.HTML
        )
        self.assertEqual(config.get_value(), "Test value")

        config2 = Configuration.objects.create(
            key="test-key2", value="", data_type=Configuration.DataType.HTML
        )
        self.assertEqual(config2.get_value(), "")

        config3 = Configuration.objects.create(
            key="test-key3",
            value='{"key" : "value"}',
            data_type=Configuration.DataType.HTML,
        )
        self.assertEqual(config3.get_value(), '{"key" : "value"}')

        config4 = Configuration.objects.create(
            key="test-key4",
            value="<p>Test value</p>",
            data_type=Configuration.DataType.HTML,
        )
        self.assertEqual(config4.get_value(), "<p>Test value</p>")

        config5 = Configuration.objects.create(
            key="test-key5",
            value="<p>{% configuration_value 'test-key' %}</p>",
            data_type=Configuration.DataType.HTML,
        )
        self.assertEqual(config5.get_value(), "<p>Test value</p>")

        config6 = Configuration.objects.create(
            key="test-key6",
            value="{% url 'homepage' %}",
            data_type=Configuration.DataType.HTML,
        )
        self.assertEqual(config6.get_value(), "/")
