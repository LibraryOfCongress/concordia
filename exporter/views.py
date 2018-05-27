import csv
from django.http import HttpResponse
from django.views.generic import TemplateView
from concordia.models import Asset, Collection, Transcription, UserAssetTagCollection, Tag


class ExportCollectionView(TemplateView):
    """
    Exports the transcription and tags to csv file

    """
    template_name = 'transcriptions/collection.html'

    def get(self, request, *args, **kwargs):
        collection = Collection.objects.get(slug=self.args[0])
        asset_list = collection.asset_set.all().order_by('title', 'sequence')
        # Create the HttpResponse object with the appropriate CSV header.
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="{0}.csv"'.format(collection.slug)
        field_names = ['title', 'description', 'media_url']
        writer = csv.writer(response)
        writer.writerow(['Collection', 'Title', 'Description', 'MediaUrl', 'Transcription', 'Tags'])
        for asset in asset_list:
            transcription = Transcription.objects.filter(asset=asset, user_id=self.request.user.id)
            if transcription:
                transcription = transcription[0].text
            else:
                transcription = ""
            tags = UserAssetTagCollection.objects.filter(asset=asset, user_id=self.request.user.id)
            if tags:
                tags = list(tags[0].tags.all().values_list('name', flat=True))
            else:
                tags = ""
            row = [collection.title] + [getattr(asset, i) for i in field_names] + [transcription, tags]
            writer.writerow(row)
        return response
