from logging import getLogger
from django.conf import settings
from django.contrib.auth import get_user_model
from registration.forms import RegistrationForm
from django import forms


User = get_user_model()
logger = getLogger(__name__)

class ConcordiaUserForm(RegistrationForm):
    password1 = forms.CharField(label="Password", required=False)
    password2 = forms.CharField(label="Password confirmation", required=False)
    first_name = forms.CharField(max_length=15, label='First name', required=False)
    last_name = forms.CharField(max_length=15, label='Last name', required=False)
    myfile = forms.FileField(required=False)

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name',]
