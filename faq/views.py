
from django.views.generic import TemplateView

from .models import FAQ


class FAQView(TemplateView):
    template_name = "faq.html"

    def get_context_data(self, **kws):
        return dict(super().get_context_data(**kws), faq=FAQ.objects.all())
