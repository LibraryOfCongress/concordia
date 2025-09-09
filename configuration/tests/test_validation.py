from django.core.exceptions import ValidationError
from django.test import TestCase

from configuration.validation import validate_rate


class TestValidation(TestCase):
    def test_valid_rates(self):
        self.assertEqual(validate_rate("1/s"), "1/s")
        self.assertEqual(validate_rate("10/m"), "10/m")
        self.assertEqual(validate_rate("100/h"), "100/h")
        self.assertEqual(validate_rate("1000/d"), "1000/d")

    def test_rate_stripping_whitespace(self):
        # Leading/trailing spaces
        self.assertEqual(validate_rate(" 10/m "), "10/m")
        self.assertEqual(validate_rate("\t10/m"), "10/m")
        self.assertEqual(validate_rate("10/m\t"), "10/m")
        self.assertEqual(validate_rate("\n10/m\n"), "10/m")
        self.assertEqual(validate_rate(" \n\t10/m\t\n "), "10/m")

        # Internal whitespace is not allowed and should still raise
        with self.assertRaises(ValidationError):
            validate_rate("10 /m")

        with self.assertRaises(ValidationError):
            validate_rate("10/ m")

        with self.assertRaises(ValidationError):
            validate_rate("10 / m")

    def test_non_string_input(self):
        with self.assertRaises(ValidationError):
            validate_rate(10)

        with self.assertRaises(ValidationError):
            validate_rate(None)

        with self.assertRaises(ValidationError):
            validate_rate(["5/m"])

    def test_invalid_format(self):
        with self.assertRaises(ValidationError):
            validate_rate("10")  # no unit

        with self.assertRaises(ValidationError):
            validate_rate("10/min")  # full word

        with self.assertRaises(ValidationError):
            validate_rate("ten/m")  # non-numeric

        with self.assertRaises(ValidationError):
            validate_rate("10/")  # missing unit

        with self.assertRaises(ValidationError):
            validate_rate("/m")  # missing number

        # This is now valid due to stripping
        self.assertEqual(validate_rate("10/m\n"), "10/m")

        with self.assertRaises(ValidationError):
            validate_rate("10/m/extra")  # too many parts

    def test_zero_or_negative_values(self):
        with self.assertRaises(ValidationError):
            validate_rate("0/s")

        with self.assertRaises(ValidationError):
            validate_rate("-5/m")

    def test_invalid_unit(self):
        with self.assertRaises(ValidationError):
            validate_rate("10/w")  # unsupported unit

        with self.assertRaises(ValidationError):
            validate_rate("10/ms")  # unsupported unit

        with self.assertRaises(ValidationError):
            validate_rate("10/seconds")  # full unit
