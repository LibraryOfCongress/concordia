import json

from django.core.cache import caches
from django.test import TestCase

from configuration.models import Configuration
from configuration.utils import (
    CONFIGURATION_KEY_PREFIX,
    cache_configuration_value,
    configuration_value,
)


class TestConfigurationUtils(TestCase):
    def setUp(self):
        self.cache = caches["configuration_cache"]
        self.cache.clear()

    def test_configuration_value(self):
        Configuration.objects.create(
            key="test-key", value="Test value", data_type=Configuration.DataType.TEXT
        )
        self.assertEqual(configuration_value("test-key"), "Test value")

        Configuration.objects.create(
            key="test-key2", value="100", data_type=Configuration.DataType.NUMBER
        )
        self.assertEqual(configuration_value("test-key2"), 100)

        Configuration.objects.create(
            key="test-key3", value="TrUe", data_type=Configuration.DataType.BOOLEAN
        )
        self.assertEqual(configuration_value("test-key3"), True)

        Configuration.objects.create(
            key="test-key4", value="", data_type=Configuration.DataType.JSON
        )
        self.assertRaises(
            json.decoder.JSONDecodeError, configuration_value, "test-key4"
        )

        Configuration.objects.create(
            key="test-key5",
            value='{"key" : "value"}',
            data_type=Configuration.DataType.JSON,
        )
        self.assertEqual(configuration_value("test-key5"), {"key": "value"})

        Configuration.objects.create(
            key="test-key6",
            value="<p>{% configuration_value 'test-key' %}</p>",
            data_type=Configuration.DataType.HTML,
        )
        self.assertEqual(configuration_value("test-key6"), "<p>Test value</p>")


class TestCacheConfigurationValue(TestCase):
    def setUp(self):
        self.cache = caches["configuration_cache"]
        self.cache.clear()

    def test_explicit_value_is_cached(self):
        key = "explicit-key"
        cached = cache_configuration_value(key, 123)
        self.assertEqual(cached, 123)
        self.assertEqual(
            self.cache.get(f"{CONFIGURATION_KEY_PREFIX}_{key}"),
            123,
        )

    def test_value_is_fetched_from_model_if_not_supplied(self):
        Configuration.objects.create(
            key="fetched-key", value="true", data_type=Configuration.DataType.BOOLEAN
        )
        cached = cache_configuration_value("fetched-key")
        self.assertEqual(cached, True)
        self.assertEqual(
            self.cache.get(f"{CONFIGURATION_KEY_PREFIX}_fetched-key"),
            True,
        )
