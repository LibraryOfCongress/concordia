from django.views.generic import TemplateView
from .models import Asset, Collection


class TranscribrView(TemplateView):
    template_name = 'transcribr/home.html'

    def get_context_data(self, **kws):
        collections = Collection.objects.all()
        return dict(
            super().get_context_data(**kws),
            collections=collections
        )


class TranscribrCollectionView(TemplateView):
    template_name = 'transcribr/collection.html'

    def get_context_data(self, **kws):
        collection = Collection.objects.get(id=self.args[0])
        return dict(
            super().get_context_data(**kws),
            collection=collection
        )


class TranscribrAssetView(TemplateView):
    template_name = 'transcribr/asset.html'
