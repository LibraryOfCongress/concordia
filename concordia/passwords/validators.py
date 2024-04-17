# coding=utf-8
# Originally from
# https://github.com/dstufft/django-passwords/blob/master/passwords/validators.py
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# Settings
PASSWORD_COMPLEXITY = getattr(settings, "PASSWORD_COMPLEXITY", None)


class ComplexityValidator(object):
    message = _("Must be more complex (%s)")
    code = "complexity"

    def __init__(self, complexities):
        self.complexities = complexities

    def __call__(self, value):
        if self.complexities is None:
            return

        uppercase, lowercase, letters = set(), set(), set()
        digits, special = set(), set()

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
                self.message % (_("must contain ") + ", ".join(errors),), code=self.code
            )
