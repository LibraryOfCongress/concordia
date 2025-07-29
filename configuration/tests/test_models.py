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

    def test_rate(self):
        # Valid rates
        config1 = Configuration.objects.create(
            key="test-key1", value="1/s", data_type=Configuration.DataType.RATE
        )
        self.assertEqual(config1.get_value(), "1/s")

        config2 = Configuration.objects.create(
            key="test-key2", value="100/m", data_type=Configuration.DataType.RATE
        )
        self.assertEqual(config2.get_value(), "100/m")

        config3 = Configuration.objects.create(
            key="test-key3", value="50/h", data_type=Configuration.DataType.RATE
        )
        self.assertEqual(config3.get_value(), "50/h")

        config4 = Configuration.objects.create(
            key="test-key4", value="1000/d", data_type=Configuration.DataType.RATE
        )
        self.assertEqual(config4.get_value(), "1000/d")

        # Invalid formats
        config5 = Configuration.objects.create(
            key="test-key5", value="5/hour", data_type=Configuration.DataType.RATE
        )
        self.assertEqual(config5.get_value(), "")

        config6 = Configuration.objects.create(
            key="test-key6", value="ten/m", data_type=Configuration.DataType.RATE
        )
        self.assertEqual(config6.get_value(), "")

        config7 = Configuration.objects.create(
            key="test-key7", value="10", data_type=Configuration.DataType.RATE
        )
        self.assertEqual(config7.get_value(), "")

        config8 = Configuration.objects.create(
            key="test-key8", value="10/", data_type=Configuration.DataType.RATE
        )
        self.assertEqual(config8.get_value(), "")

        config9 = Configuration.objects.create(
            key="test-key9", value="/m", data_type=Configuration.DataType.RATE
        )
        self.assertEqual(config9.get_value(), "")

        # Zero and negative values
        config10 = Configuration.objects.create(
            key="test-key10", value="0/s", data_type=Configuration.DataType.RATE
        )
        self.assertEqual(config10.get_value(), "")

        config11 = Configuration.objects.create(
            key="test-key11", value="-5/m", data_type=Configuration.DataType.RATE
        )
        self.assertEqual(config11.get_value(), "")

        # Empty value
        config12 = Configuration.objects.create(
            key="test-key12", value="", data_type=Configuration.DataType.RATE
        )
        self.assertEqual(config12.get_value(), "")
