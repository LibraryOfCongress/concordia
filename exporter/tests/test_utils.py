from django.test import TestCase

from exporter.exceptions import UnacceptableCharacterError
from exporter.utils import (
    find_unacceptable_characters,
    is_acceptable_character,
    validate_text_for_export,
)


class UtilsValidationTests(TestCase):
    def test_printable_ascii_is_acceptable(self):
        self.assertTrue(is_acceptable_character("A"))
        self.assertTrue(is_acceptable_character("9"))
        self.assertTrue(is_acceptable_character(" "))

    def test_whitelisted_nonprintable_is_acceptable(self):
        # Tab (\t) and NBSP (\xa0) are explicitly whitelisted
        self.assertTrue(is_acceptable_character("\t"))
        self.assertTrue(is_acceptable_character("\xa0"))

    def test_control_char_is_rejected(self):
        self.assertFalse(is_acceptable_character("\x00"))
        self.assertFalse(is_acceptable_character("\x1f"))

    def test_find_unacceptable_characters_returns_positions(self):
        sample = "ok\nBad\x00line\nnext\tgood"
        violations = find_unacceptable_characters(sample)
        # Expect the single null-byte at line 2, column 4 (1-based)
        self.assertEqual(violations, [(2, 4, "\x00")])

    def test_duplicate_violations_are_recorded(self):
        sample = "a\x00b\x00"  # two null bytes same line
        violations = find_unacceptable_characters(sample)
        self.assertEqual(violations, [(1, 2, "\x00"), (1, 4, "\x00")])

    def test_validate_text_for_export_passes_clean_text(self):
        clean = "Hello world!\nThis\u3000is ok."
        # \u3000 (ideographic space) is whitelisted
        self.assertTrue(validate_text_for_export(clean))

    def test_validate_text_for_export_raises_on_bad_text(self):
        bad = "Bad\u200bText"  # zero-width space is not allowed
        with self.assertRaises(UnacceptableCharacterError) as cm:
            validate_text_for_export(bad)
        err = cm.exception
        self.assertEqual(err.violations, [(1, 4, "\u200b")])
