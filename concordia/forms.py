from django.contrib.auth import get_user_model
from registration.forms import RegistrationForm

User = get_user_model()


class ConcordiaUserForm(RegistrationForm):
    
    class Meta:
        model = User
        fields = ['username', 'email']

