from unittest.mock import MagicMock, patch

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.http import HttpRequest
from django.test import TestCase

from concordia.views.decorators import next_asset_rate


class TestNextAssetRate(TestCase):
    def setUp(self):
        self.request = HttpRequest()

    def test_authenticated_user_returns_none(self):
        self.request.user = MagicMock(is_authenticated=True)
        result = next_asset_rate("any.group", self.request)
        self.assertIsNone(result)

    @patch("concordia.views.decorators.configuration_value")
    @patch("concordia.views.decorators.validate_rate")
    def test_anonymous_user_valid_rate(self, mock_validate_rate, mock_config_value):
        self.request.user = MagicMock(is_authenticated=False)
        mock_config_value.return_value = "10/m"
        mock_validate_rate.return_value = "10/m"

        result = next_asset_rate("next_asset", self.request)
        self.assertEqual(result, "10/m")

    @patch("concordia.views.decorators.configuration_value")
    @patch("concordia.views.decorators.validate_rate")
    def test_anonymous_user_invalid_rate_falls_back(
        self, mock_validate_rate, mock_config_value
    ):
        self.request.user = MagicMock(is_authenticated=False)
        mock_config_value.return_value = "invalid"
        mock_validate_rate.side_effect = ValidationError("bad")

        result = next_asset_rate("next_asset", self.request)
        self.assertEqual(result, "4/m")

    @patch("concordia.views.decorators.configuration_value")
    def test_anonymous_user_missing_value_falls_back(self, mock_config_value):
        self.request.user = MagicMock(is_authenticated=False)
        mock_config_value.side_effect = ObjectDoesNotExist()

        result = next_asset_rate("next_asset", self.request)
        self.assertEqual(result, "4/m")
