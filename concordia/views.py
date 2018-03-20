from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin

from registration.backends.simple.views import RegistrationView
from .forms import ConcordiaUserForm


class ConcordiaRegistrationView(RegistrationView):
    form_class = ConcordiaUserForm


class AccountProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'profile.html'

    def get_context_data(self, **kws):
        return dict(
            super().get_context_data(**kws),
        )
