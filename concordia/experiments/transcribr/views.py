from django.views.generic import TemplateView

class TranscribrView(TemplateView):
    template_name = 'transcribr/experiment.html'
