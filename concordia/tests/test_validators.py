from django.core.exceptions import ValidationError
from django.test import TestCase

from concordia.validators import DjangoPasswordsValidator


class TestValidators(TestCase):
    def test_DjangoPasswordsValidator(self):
        validator = DjangoPasswordsValidator()
        expected_error = "Must be more complex (%s)"
        self.assertIsNone(validator.validate("Ab1!"))

        expected_suberror = "must contain 1 or more unique lowercase characters"
        with self.assertRaises(ValidationError) as cm:
            validator.validate("AB1!")
        self.assertEqual(cm.exception.messages, [expected_error % expected_suberror])
        self.assertEqual(cm.exception.error_list[0].code, "complexity")

        expected_suberror = "must contain 1 or more unique uppercase characters"
        with self.assertRaises(ValidationError) as cm:
            validator.validate("ab1!")
        self.assertEqual(cm.exception.messages, [expected_error % expected_suberror])
        self.assertEqual(cm.exception.error_list[0].code, "complexity")

        expected_suberror = "must contain 1 or more unique digits"
        with self.assertRaises(ValidationError) as cm:
            validator.validate("Ab!")
        self.assertEqual(cm.exception.messages, [expected_error % expected_suberror])
        self.assertEqual(cm.exception.error_list[0].code, "complexity")

        expected_suberror = "must contain 1 or more non unique special characters"
        with self.assertRaises(ValidationError) as cm:
            validator.validate("Ab1")
        self.assertEqual(cm.exception.messages, [expected_error % expected_suberror])
        self.assertEqual(cm.exception.error_list[0].code, "complexity")

        self.assertEqual(
            validator.get_help_text(),
            "Your password fails to meet our complexity requirements.",
        )
