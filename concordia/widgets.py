from django import forms


class EmailWidget(forms.EmailInput):
    template_name = "forms/widgets/email.html"
