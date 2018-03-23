import requests
from django.conf import settings
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin

from registration.backends.simple.views import RegistrationView
from .forms import ConcordiaUserForm
from transcribr.models import Asset, Collection


def transcribr_api(relative_path):
    abs_path = '{}/api/v1/{}'.format(
        settings.TRANSCRIBR['netloc'],
        relative_path
    )
    return requests.get(abs_path).json()


class ConcordiaRegistrationView(RegistrationView):
    form_class = ConcordiaUserForm


class AccountProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'profile.html'

    def get_context_data(self, **kws):
        return dict(
            super().get_context_data(**kws),
        )


class TranscribrView(TemplateView):
    template_name = 'transcriptions/home.html'

    def get_context_data(self, **kws):
        collections = transcribr_api('collections/')
        return dict(
            super().get_context_data(**kws),
            collections=collections
        )


class TranscribrCollectionView(TemplateView):
    template_name = 'transcriptions/collection.html'

    def get_context_data(self, **kws):
        collection = Collection.objects.get(slug=self.args[0])
        return dict(
            super().get_context_data(**kws),
            collection=collection
        )


class TranscribrAssetView(TemplateView):
    template_name = 'transcriptions/asset.html'

    def get_context_data(self, **kws):
        asset = Asset.objects.get(collection__slug=self.args[0], slug=self.args[1])
        return dict(
            super().get_context_data(**kws),
            asset=asset
        )
