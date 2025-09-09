from django.test import TestCase

from exporter.exceptions import UnacceptableCharacterError
from exporter.utils import (
    find_unacceptable_characters,
    is_acceptable_character,
    remove_unacceptable_characters,
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

    def test_remove_unacceptable_characters_removes_disallowed_chars(self):
        # Mix of unacceptable characters across positions.
        sample = "\x00Start\u200bMiddleEnd\x1f"
        cleaned = remove_unacceptable_characters(sample)
        self.assertEqual(cleaned, "StartMiddleEnd")

    def test_remove_unacceptable_characters_keeps_whitelisted_chars(self):
        # Ensure whitelist is honored: \t, NBSP, ideographic space, em space.
        sample = "A\tB\xa0C\u3000D\u2003E"
        cleaned = remove_unacceptable_characters(sample)
        self.assertEqual(cleaned, sample)

    def test_remove_unacceptable_characters_preserves_newlines_and_crlf(self):
        # Preserve exact newline forms while removing bad chars within lines.
        sample = "one\r\ntwo\nthree\rfour"
        # Insert a zero-width space in "two" and a NUL at end of "three".
        sample_with_bad = "one\r\nt\u200bwo\nthree\x00\rfour"
        cleaned = remove_unacceptable_characters(sample_with_bad)
        self.assertEqual(cleaned, sample)

    def test_remove_unacceptable_characters_noop_on_clean_text(self):
        clean = "Line 1\nLine 2\tTabbed\u3000Ideographic\u2003Em"
        cleaned = remove_unacceptable_characters(clean)
        self.assertEqual(cleaned, clean)

    def test_remove_unacceptable_characters_handles_multiple_lines(self):
        # Multiple lines with several unacceptable chars per line.
        sample = (
            "ok line\n"
            "bad\x00line\x00with\x00many\n"
            "zero\u200bwidth\u200bspaces\n"
            "\x00\x00start and end\u200b"
        )
        cleaned = remove_unacceptable_characters(sample)
        self.assertEqual(
            cleaned, "ok line\n" "badlinewithmany\n" "zerowidthspaces\n" "start and end"
        )

    def test_remove_unacceptable_characters_preserves_carriage_return_alone(self):
        # Some inputs may include bare '\r' (classic Mac, or copy/paste artifacts).
        sample = "a\rb\rc"
        # Add disallowed chars around to ensure we only drop them, not '\r'.
        sample_with_bad = "a\x00\rb\u200b\rc\x1f"
        cleaned = remove_unacceptable_characters(sample_with_bad)
        self.assertEqual(cleaned, sample)
