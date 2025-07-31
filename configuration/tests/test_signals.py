from django.core.cache import caches
from django.test import TestCase

from configuration.models import Configuration


class TestConfigurationSignal(TestCase):
    def setUp(self):
        caches["configuration_cache"].clear()

    def test_signal_caches_valid_value(self):
        Configuration.objects.create(
            key="signal-key",
            value="42",
            data_type=Configuration.DataType.NUMBER,
        )
        self.assertEqual(caches["configuration_cache"].get("config_signal-key"), 42)

    def test_signal_does_not_cache_invalid_json(self):
        Configuration.objects.create(
            key="signal-json-invalid",
            value="not valid json",
            data_type=Configuration.DataType.JSON,
        )
        # Should not raise, but value should not be cached
        self.assertIsNone(
            caches["configuration_cache"].get("config_signal-json-invalid")
        )
