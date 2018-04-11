from logging import getLogger
import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from registration.backends.simple.views import RegistrationView
from .forms import ConcordiaUserForm
from transcribr.models import Asset, Collection, Transcription
from django.core.paginator import Paginator
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

logger = getLogger(__name__)

ASSETS_PER_PAGE = 36

def transcribr_api(relative_path):
    abs_path = '{}/api/v1/{}'.format(
        settings.TRANSCRIBR['netloc'],
        relative_path
    )
    logger.debug('Calling API path {}'.format(abs_path))
    data = requests.get(abs_path).json()

    logger.debug('Received {}'.format(data))
    return data


class ConcordiaRegistrationView(RegistrationView):
    form_class = ConcordiaUserForm


class AccountProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'profile.html'

    def get_context_data(self, **kws):
        return super().get_context_data(**dict(
            kws,
            transcriptions=Transcription.objects.filter(user_id=self.request.user.id)
        ))


class TranscribrView(TemplateView):
    template_name = 'transcriptions/home.html'

    def get_context_data(self, **kws):
        response = transcribr_api('collections/')
        return dict(
            super().get_context_data(**kws),
            response=response
        )


class TranscribrCollectionView(TemplateView):
    template_name = 'transcriptions/collection.html'

    def get_context_data(self, **kws):
        collection = Collection.objects.get(slug=self.args[0])
        asset_list = collection.asset_set.all()
        paginator = Paginator(asset_list, ASSETS_PER_PAGE)

        if not self.request.GET.get('page'):
            page = 1
        else:
            page = self.request.GET.get('page')

        assets = paginator.get_page(page)

        return dict(
            super().get_context_data(**kws),
            collection=collection,
            assets=assets
        )

@method_decorator(csrf_exempt, name='dispatch')
class TranscribrAssetView(TemplateView):
    template_name = 'transcriptions/asset.html'

    def post(self, request, *args, **kwargs):
        context = self.get_context_data()
        Transcription.objects.create(asset=context['asset'], text=request.POST['tx'], user_id=1)

        return super(TemplateView, self).render_to_response(context)

    def get_context_data(self, **kws):
        asset = Asset.objects.get(collection__slug=self.args[0], slug=self.args[1])
        transcription = Transcription.objects.latest('created_on')

        return dict(
            super().get_context_data(**kws),
            asset=asset,
            transcription=transcription
        )

class TranscriptionView(TemplateView):
    template_name = 'transcriptions/transcription.html'

    def get_context_data(self, **kws):
        transcription = Transcription.objects.get(id=self.args[0])
        transcription_user = get_user_model().objects.get(id=transcription.id)
        return super().get_context_data(**dict(
            kws,
            transcription=transcription,
            transcription_user=transcription_user
        ))


class ToDoView(TemplateView):
    template_name = 'todo.html'


class ExperimentsView(TemplateView):

    def get_template_names(self):
        return ['experiments/{}.html'.format(self.args[0])]
