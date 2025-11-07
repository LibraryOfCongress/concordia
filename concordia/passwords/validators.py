"""
Password complexity validator.

This module provides a `ComplexityValidator` compatible with Django’s validation
pipeline. It checks a password against configurable complexity requirements,
counting unique characters of several categories and optionally unique words.

Settings:
    PASSWORD_COMPLEXITY (dict[str, int] | None):
        Mapping of requirement names to minimum counts. Any missing keys default
        to 0. If the setting is falsy or not provided, no complexity checks run.

        Supported keys:
            - 'UPPER'   : unique uppercase letters
            - 'LOWER'   : unique lowercase letters
            - 'LETTERS' : unique letters (upper or lower)
            - 'DIGITS'  : unique digits
            - 'SPECIAL' : unique non-space, non-alnum characters
            - 'WORDS'   : unique word tokens (\\b\\w+ with re.UNICODE)

Usage:
    In your Django settings:

        AUTH_PASSWORD_VALIDATORS = [
            {
                "NAME":
                "concordia.passwords.validators.ComplexityValidator",
                "OPTIONS": {
                    "complexities": {
                        "UPPER": 1,
                        "LOWER": 1,
                        "DIGITS": 1,
                        "SPECIAL": 1,
                        "LETTERS": 4,
                        "WORDS": 2,
                    }
                },
            },
        ]

"""

# Originally from
# https://github.com/dstufft/django-passwords/blob/master/passwords/validators.py
import re
from typing import Mapping, Set

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# Settings
PASSWORD_COMPLEXITY = getattr(settings, "PASSWORD_COMPLEXITY", None)


class ComplexityValidator(object):
    """
    Validate password complexity against configured unique-count thresholds.

    The validator counts unique characters in several categories (uppercase,
    lowercase, letters, digits, special) and unique words, then compares those
    counts to thresholds provided at construction time.

    Attributes:
        message (str):
            Base error message template. Interpolated with a comma-separated
            list of failed requirements.
        code (str):
            Error code used in `ValidationError`.
        complexities (dict[str, int] | None):
            Thresholds for each category. When `None`, the validator is
            effectively disabled.
    """

    message = _("Must be more complex (%s)")
    code = "complexity"

    def __init__(self, complexities: Mapping[str, int] | None):
        """
        Initialize the validator.

        Args:
            complexities (Mapping[str, int] | None):
                Per-category minimum unique counts. If `None`, no checks are
                enforced. Missing keys default to 0.
        """
        self.complexities = complexities

    def __call__(self, value: str) -> None:
        """
        Validate a password string.

        The method tallies unique characters by category using `str.isupper`,
        `str.islower`, `str.isdigit`, and a fallback for non-space, non-alnum
        characters, and counts unique words via `re.findall(r"\\b\\w+", ...)`.

        Args:
            value (str): The candidate password.

        Raises:
            ValidationError:
                If one or more configured thresholds are not met. The error
                message lists each failed requirement.
        """
        if self.complexities is None:
            return

        uppercase: Set[str] = set()
        lowercase: Set[str] = set()
        letters: Set[str] = set()
        digits: Set[str] = set()
        special: Set[str] = set()

        for character in value:
            if character.isupper():
                uppercase.add(character)
                letters.add(character)
            elif character.islower():
                lowercase.add(character)
                letters.add(character)
            elif character.isdigit():
                digits.add(character)
            elif not character.isspace():
                special.add(character)

        words = set(re.findall(r"\b\w+", value, re.UNICODE))

        errors = []
        if len(uppercase) < self.complexities.get("UPPER", 0):
            errors.append(
                _("%(UPPER)s or more unique uppercase characters") % self.complexities
            )
        if len(lowercase) < self.complexities.get("LOWER", 0):
            errors.append(
                _("%(LOWER)s or more unique lowercase characters") % self.complexities
            )
        if len(letters) < self.complexities.get("LETTERS", 0):
            errors.append(_("%(LETTERS)s or more unique letters") % self.complexities)
        if len(digits) < self.complexities.get("DIGITS", 0):
            errors.append(_("%(DIGITS)s or more unique digits") % self.complexities)
        if len(special) < self.complexities.get("SPECIAL", 0):
            errors.append(
                _("%(SPECIAL)s or more non unique special characters")
                % self.complexities
            )
        if len(words) < self.complexities.get("WORDS", 0):
            errors.append(_("%(WORDS)s or more unique words") % self.complexities)

        if errors:
            raise ValidationError(
                self.message % (_("must contain ") + ", ".join(errors),),
                code=self.code,
            )
