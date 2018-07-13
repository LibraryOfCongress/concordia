from logging import getLogger

from django import forms
from django.contrib.auth import get_user_model
from registration.forms import RegistrationForm

User = get_user_model()
logger = getLogger(__name__)
ROLE_CHOICES = (("admin", ("Admin")), ("cm", ("Content Manager")), ("user", ("User")))


class ConcordiaUserForm(RegistrationForm):
    username = forms.CharField(
        label="Username",
        required=True,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Username"}
        ),
    )
    email = forms.CharField(
        label="Email",
        required=True,
        widget=forms.EmailInput(
            attrs={"class": "form-control", "placeholder": "Email"}
        ),
    )
    password1 = forms.CharField(
        label="Password",
        required=True,
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "Password"}
        ),
    )
    password2 = forms.CharField(
        label="Confirm",
        required=True,
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "Confirm"}
        ),
    )

    class Meta:
        model = User
        fields = ["username", "email"]

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
