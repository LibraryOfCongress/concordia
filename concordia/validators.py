from django.conf import settings
from django.utils.translation import gettext_lazy as _
from passwords.validators import ComplexityValidator


class DjangoPasswordsValidator(object):
    """
    Wrapper for the django-passwords complexity validator which is compatible
    with the Django 1.9+ password validation API
    """

    message = _("Must be more complex (%s)")
    code = "complexity"

    def __init__(self):
        self.validator = ComplexityValidator(settings.PASSWORD_COMPLEXITY)

    def get_help_text(self):
        return _("Your password fails to meet our complexity requirements.")

    def validate(self, value, user=None):
        return self.validator(value)
