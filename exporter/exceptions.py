from typing import List, Tuple


class UnacceptableCharacterError(ValueError):
    """
    Raised when unacceptable characters are discovered in text to be exported.

    Each violation is stored so that callers can inspect which line / column held
    the character.

    Args:
        violations: A list of `(line, column, character)` triples representing
            every disallowed character found.  Line and column numbers are both
            **1-based** so they can be reported directly to users.
    """

    def __init__(self, violations: List[Tuple[int, int, str]]):
        self.violations: List[Tuple[int, int, str]] = violations
        details = ", ".join(
            f"line {ln} col {col} -> {ch!r}" for ln, col, ch in violations
        )
        super().__init__(f"Unacceptable characters found: {details}")
