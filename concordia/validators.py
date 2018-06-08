import re

from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _


PASSWORD_COMPLEXITY = { # You can omit any or all of these for no limit for that particular set
    "UPPER": 1,        # Uppercase
    "LOWER": 1,        # Lowercase
    "LETTERS": 1,       # Either uppercase or lowercase letters
    "DIGITS": 1,       # Digits
    "SPECIAL": 1,      # Not alphanumeric, space or punctuation character
    "WORDS": 1         # Words (alphanumeric sequences separated by a whitespace or punctuation character)
}


class ComplexityValidator(object):
    message = _("Must be more complex (%s)")
    code = "complexity"

    def __init__(self):
        self.complexities = PASSWORD_COMPLEXITY

    def validate(self, value, user=None):
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

        words = set(re.findall(r'\b\w+', value, re.UNICODE))

        errors = []
        if len(uppercase) < self.complexities.get("UPPER", 0):
            errors.append(
                _("%(UPPER)s or more unique uppercase characters") %
                self.complexities)
        if len(lowercase) < self.complexities.get("LOWER", 0):
            errors.append(
                _("%(LOWER)s or more unique lowercase characters") %
                self.complexities)
        if len(letters) < self.complexities.get("LETTERS", 0):
            errors.append(
                _("%(LETTERS)s or more unique letters") %
                self.complexities)
        if len(digits) < self.complexities.get("DIGITS", 0):
            errors.append(
                _("%(DIGITS)s or more unique digits") %
                self.complexities)
        if len(special) < self.complexities.get("SPECIAL", 0):
            errors.append(
                _("%(SPECIAL)s or more non unique special characters") %
                self.complexities)
        if len(words) < self.complexities.get("WORDS", 0):
            errors.append(
                _("%(WORDS)s or more unique words") %
                self.complexities)

        if errors:
            raise ValidationError(self.message % (_(u'must contain ') + u', '.join(errors),),
                                  code=self.code)

complexity = ComplexityValidator
