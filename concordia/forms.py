from logging import getLogger

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from registration.forms import RegistrationForm

User = get_user_model()
logger = getLogger(__name__)
ROLE_CHOICES = (("admin", ("Admin")), ("cm", ("Content Manager")), ("user", ("User")))


class ConcordiaUserForm(RegistrationForm):
    password1 = forms.CharField(
        label="Password", required=False, widget=forms.PasswordInput()
    )
    password2 = forms.CharField(
        label="Password confirmation", required=False, widget=forms.PasswordInput()
    )
    first_name = forms.CharField(max_length=15, label="First name", required=False)
    last_name = forms.CharField(max_length=15, label="Last name", required=False)
    role = forms.CharField(
        label="Role", widget=forms.RadioSelect(choices=ROLE_CHOICES), required=False
    )

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name"]

    def save(self, commit=True):
        instance = super(ConcordiaUserForm, self).save(commit=False)
        role_dict = {"admin": "is_superuser", "cm": "is_staff", "user": "is_active"}
        if "role" in self.data and self.data["role"] in role_dict:
            role = self.data["role"]
            if role == "admin":
                setattr(instance, "is_staff", 1)
            setattr(instance, role_dict[role], 1)
        if commit:
            instance.save()
        return instance


class ConcordiaUserEditForm(ConcordiaUserForm):
    myfile = forms.FileField(required=False)
