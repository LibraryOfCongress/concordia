from logging import getLogger
from django.contrib.auth import get_user_model
from registration.forms import RegistrationForm
from django import forms


User = get_user_model()
logger = getLogger(__name__)


class ConcordiaUserForm(RegistrationForm):
    password1 = forms.CharField(label="Password", required=False)
    password2 = forms.CharField(label="Password confirmation", required=False)

    class Meta:
        model = User
        fields = ['username', 'email']