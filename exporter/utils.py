"""
Utility helpers for validating outgoing text.

The primary public entry-point is `exporter.utils.validate_text_for_export`,
which raises an `exporter.exceptions.UnacceptableCharacterError` when any
non-printable Unicode character is detected.  Validation is performed per
line so the caller receives the exact location of every problem character.
"""

from typing import List, Tuple

from exporter.exceptions import UnacceptableCharacterError

_WHITELIST = [
    "\t",  # Tab
    "\xa0",  # Non-breaking space
    "\u3000",  # Ideographic space; used in Chinese/Japanese/Korean
    "\u2003",  # em space (space the width of the 'm' character)
]


def is_acceptable_character(character: str) -> bool:
    """
    Return `True` when `character` is considered printable.

    The function simply wraps `str.isprintable()` so behaviour stays in sync
    with the official Unicode definition of *printable*.

    Args:
        character: A single Unicode character.

    Returns:
        `True` if the character is printable; otherwise `False`.
    """

    return character.isprintable() or character in _WHITELIST


def find_unacceptable_characters(text: str) -> List[Tuple[int, int, str]]:
    """
    Locate every non-printable character in *text*.

    The scan is performed line by line so that the exact position (line and
    column) of each offending character can be fed back to the caller.

    Args:
        text: The string to validate.

    Returns:
        A list of `(line_number, column_number, character)` triples.  The list
        may contain duplicates because each instance of an invalid character is
        recorded individually.
    """

    violations: List[Tuple[int, int, str]] = []

    for line_no, line in enumerate(text.splitlines(), start=1):
        for col_no, ch in enumerate(line, start=1):
            if not is_acceptable_character(ch):
                violations.append((line_no, col_no, ch))

    return violations


def validate_text_for_export(text: str) -> bool:
    """
    Validate `text` and raise if it contains any unacceptable characters.

    Args:
        text: The text destined for export.

    Returns:
        `True` if the text is valid for export

    Raises:
        UnacceptableCharacterError: If at least one non-printable character is
        found.
    """

    violations = find_unacceptable_characters(text)
    if violations:
        raise UnacceptableCharacterError(violations)
    return True
