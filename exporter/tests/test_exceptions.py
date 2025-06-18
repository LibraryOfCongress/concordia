from django.test import TestCase

from exporter.exceptions import UnacceptableCharacterError


class UnacceptableCharacterErrorTests(TestCase):
    def test_violations_are_stored(self):
        """The `violations` list passed to `__init__` is stored unmodified."""
        violations = [(2, 3, "\u200b"), (4, 1, "\x00")]
        err = UnacceptableCharacterError(violations)
        self.assertEqual(err.violations, violations)

    def test_message_contains_formatted_details(self):
        """The exception message should embed a human-readable summary."""
        violations = [(1, 1, "\x00")]
        err = UnacceptableCharacterError(violations)
        msg = str(err)
        self.assertIn("line 1 col 1", msg)
        # The backslash in "\\x00" is escaped once by repr() and once in the
        # string literal, so we search for the double-escaped form.
        self.assertIn("\\x00", msg)
