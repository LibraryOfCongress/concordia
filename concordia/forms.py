from django.conf import settings
from django.contrib.auth import get_user_model
from registration.forms import RegistrationForm

User = get_user_model()


class ConcordiaUserForm(RegistrationForm):
    
    class Meta:
        model = User
        fields = ['username', 'email']

    def save(self, *args, **kws):
        user = super().save(*args, **kws)
        if settings.DEBUG:
            if user.email.endswith(('@loc.gov', '@artemisconsultinginc.com')):
                user.is_superuser = True
                user.is_staff = True
                user.save()

        return user
