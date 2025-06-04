from django.core.cache import caches
from django.http import JsonResponse
from django.views import View


class VisualizationDataView(View):
    """
    Serve cached visualization data as JSON, returning a 404 JSON error if missing.

    A single endpoint that, given a `name` slug in the URL, looks up exactly
    that key in the 'visualization_cache' and returns its contents as JSON.
    If no entry exists under that key, responds with a 404 and a JSON error message.

    Attributes:
        cache (BaseCache): The Django cache used to retrieve data.

    URL Parameters:
        name (str): The slug identifying which visualization data to return.
            Example: "daily-transcription-activity-by-campaign".

    Returns:
        JsonResponse:
            - On success: the cached data (any JSON-serializable structure).
            - On failure: a JSON object {"error": "..."} with HTTP status 404.
    """

    cache = caches["visualization_cache"]

    def get(self, request, name):
        data = self.cache.get(name)
        if data is None:
            return JsonResponse(
                {"error": f"No visualization data found for '{name}'"}, status=404
            )

        return JsonResponse(data)
