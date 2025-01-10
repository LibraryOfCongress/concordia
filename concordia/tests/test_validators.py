import string

from django.core.exceptions import ValidationError
from django.test import TestCase

from concordia.passwords.validators import ComplexityValidator
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


class ComplexityValidatorTests(TestCase):
    def assertValid(self, validator, string):
        try:
            validator(string)
        except ValidationError:
            self.fail(f"String {string} failed validation unexpectedly")

    def assertInvalid(self, validator, string):
        self.assertRaises(ValidationError, validator, string)

    def make_validator(self, **complexities):
        return ComplexityValidator(complexities=complexities)

    def test_empty_validator(self):
        validator = ComplexityValidator(complexities=None)
        self.assertValid(validator, "")

    def test_minimum_uppercase_count(self):
        validator = self.make_validator(UPPER=0)
        self.assertValid(validator, "no uppercase")
        self.assertValid(validator, "Some UpperCase")
        self.assertValid(validator, "ALL UPPERCASE")

        validator = self.make_validator(UPPER=1)
        self.assertInvalid(validator, "no uppercase")
        self.assertValid(validator, "Some UpperCase")
        self.assertValid(validator, "ALL UPPERCASE")

        validator = self.make_validator(UPPER=100)
        self.assertInvalid(validator, "no uppercase")
        self.assertInvalid(validator, "Some UpperCase")
        self.assertInvalid(validator, "ALL UPPERCASE")

    def test_minimum_lowercase_count(self):
        validator = self.make_validator(LOWER=0)
        self.assertValid(validator, "NO LOWERCASE")
        self.assertValid(validator, "sOME lOWERCASE")
        self.assertValid(validator, "all lowercase")

        validator = self.make_validator(LOWER=1)
        self.assertInvalid(validator, "NO LOWERCASE")
        self.assertValid(validator, "sOME lOWERCASE")
        self.assertValid(validator, "all lowercase")

        validator = self.make_validator(LOWER=100)
        self.assertInvalid(validator, "NO LOWERCASE")
        self.assertInvalid(validator, "sOME lOWERCASE")
        self.assertInvalid(validator, "all lowercase")

    def test_minimum_letter_count(self):
        validator = self.make_validator(LETTERS=0)
        self.assertValid(validator, "1234. ?")
        self.assertValid(validator, "soME 123")
        self.assertValid(validator, "allletters")

        validator = self.make_validator(LETTERS=1)
        self.assertInvalid(validator, "1234. ?")
        self.assertValid(validator, "soME 123")
        self.assertValid(validator, "allletters")

        validator = self.make_validator(LETTERS=100)
        self.assertInvalid(validator, "1234. ?")
        self.assertInvalid(validator, "soME 123")
        self.assertInvalid(validator, "allletters")

    def test_minimum_digit_count(self):
        validator = self.make_validator(DIGITS=0)
        self.assertValid(validator, "")
        self.assertValid(validator, "0")
        self.assertValid(validator, "1")
        self.assertValid(validator, "11")
        self.assertValid(validator, "one 1")

        validator = self.make_validator(DIGITS=1)
        self.assertInvalid(validator, "")
        self.assertValid(validator, "0")
        self.assertValid(validator, "1")
        self.assertValid(validator, "11")
        self.assertValid(validator, "one 1")

    def test_minimum_punctuation_count(self):
        none = "no punctuation"
        one = "ffs!"
        mixed = r"w@oo%lo(om!ol~oo&"
        allpunc = string.punctuation

        validator = self.make_validator(SPECIAL=0)
        self.assertValid(validator, none)
        self.assertValid(validator, one)
        self.assertValid(validator, mixed)
        self.assertValid(validator, allpunc)

        validator = self.make_validator(SPECIAL=1)
        self.assertInvalid(validator, none)
        self.assertValid(validator, one)
        self.assertValid(validator, mixed)
        self.assertValid(validator, allpunc)

        validator = self.make_validator(SPECIAL=100)
        self.assertInvalid(validator, none)
        self.assertInvalid(validator, one)
        self.assertInvalid(validator, mixed)
        self.assertInvalid(validator, allpunc)

    def test_minimum_nonascii_count(self):
        none = "regularchars and numbers 100"
        one = "\x00"  # null
        many = "\x00\x01\x02\x03\x04\x05\t\n\r"

        validator = self.make_validator(SPECIAL=0)
        self.assertValid(validator, none)
        self.assertValid(validator, one)
        self.assertValid(validator, many)

        validator = self.make_validator(SPECIAL=1)
        self.assertInvalid(validator, none)
        self.assertValid(validator, one)
        self.assertValid(validator, many)

        validator = self.make_validator(SPECIAL=100)
        self.assertInvalid(validator, none)
        self.assertInvalid(validator, one)
        self.assertInvalid(validator, many)

    def test_minimum_words_count(self):
        none = ""
        one = "oneword"
        some = "one or two words"
        many = "a b c d e f g h i 1 2 3 4 5 6 7 8 9 { $ # ! )}"

        validator = self.make_validator(WORDS=0)
        self.assertValid(validator, none)
        self.assertValid(validator, one)
        self.assertValid(validator, some)
        self.assertValid(validator, many)

        validator = self.make_validator(WORDS=1)
        self.assertInvalid(validator, none)
        self.assertValid(validator, one)
        self.assertValid(validator, some)
        self.assertValid(validator, many)

        validator = self.make_validator(WORDS=10)
        self.assertInvalid(validator, none)
        self.assertInvalid(validator, one)
        self.assertInvalid(validator, some)
        self.assertValid(validator, many)

        validator = self.make_validator(WORDS=100)
        self.assertInvalid(validator, none)
        self.assertInvalid(validator, one)
        self.assertInvalid(validator, some)
        self.assertInvalid(validator, many)
