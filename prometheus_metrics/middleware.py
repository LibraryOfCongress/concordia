from timeit import default_timer

from django.utils.deprecation import MiddlewareMixin
from prometheus_client import Counter, Histogram

requests_total = Counter(
    "django_http_requests_total",
    "Total count of requests",
    ["status_code", "method", "view"],
)
requests_latency = Histogram(
    "django_http_requests_latency_seconds",
    "Histogram of requests processing time",
    ["status_code", "method", "view"],
)


class PrometheusBeforeMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.prometheus_middleware_request_start = default_timer()

    def process_response(self, request, response):
        resolver_match = request.resolver_match
        if resolver_match:
            handler = resolver_match.url_name
            if not handler:
                handler = resolver_match.view_name
            handler = handler.replace("-", "_")
        else:
            handler = "<unnamed view>"

        requests_total.labels(response.status_code, request.method, handler).inc()

        if hasattr(request, "prometheus_middleware_request_start"):
            requests_latency.labels(
                response.status_code, request.method, handler
            ).observe(default_timer() - request.prometheus_middleware_request_start)
        return response
