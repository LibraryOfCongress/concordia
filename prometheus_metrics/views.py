import prometheus_client
from django.http import HttpResponse
from django.views import View


class MetricsView(View):
    def get(self, request, *args, **kwargs):
        metrics_page = prometheus_client.generate_latest()
        return HttpResponse(
            metrics_page, content_type=prometheus_client.CONTENT_TYPE_LATEST
        )
