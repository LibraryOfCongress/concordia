from logging import getLogger

from captcha.fields import CaptchaField
from django import forms
from django.contrib.auth import get_user_model
from registration.forms import RegistrationForm

User = get_user_model()
logger = getLogger(__name__)


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
    username = forms.CharField(
        label="Username",
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Username"}
        ),
    )
    email = forms.CharField(
        label="Email",
        required=False,
        widget=forms.EmailInput(
            attrs={"class": "form-control", "placeholder": "Email"}
        ),
    )
    password1 = forms.CharField(
        label="Password",
        required=False,
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "Password"}
        ),
    )
    password2 = forms.CharField(
        label="Confirm",
        required=False,
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "Confirm"}
        ),
    )


class ConcordiaContactUsForm(forms.Form):
    email = forms.CharField(
        label="Your email",
        required=True,
        widget=forms.EmailInput(attrs={"class": "form-control"}),
    )

    subject = forms.CharField(
        label="Subject",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    category = forms.CharField(
        label="Category",
        required=True,
        widget=forms.Select(
            choices=(
                ("General", "General"),
                ("Campaign", "Question about campaign"),
                ("Problem", "Something is not working"),
            ),
            attrs={"class": "form-control"},
        ),
    )

    link = forms.CharField(
        label="Link to the page you need support with",
        required=False,
        widget=forms.URLInput(attrs={"class": "form-control"}),
    )

    story = forms.CharField(
        label="Why are you contacting us",
        required=True,
        widget=forms.Textarea(attrs={"class": "form-control"}),
    )


class CaptchaEmbedForm(forms.Form):
    captcha = CaptchaField()
