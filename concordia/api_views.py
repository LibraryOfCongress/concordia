"""
Very simple generic API views

These provide base classes for Django CBVs which behave differently when the URL
ends with ".json".

You register the view twice in urls.py and it will default to the stock Django
behaviour for the non-JSON endpoint:

    path("transcribe/", views.TranscribeListView.as_view()),
    path("transcribe.json", views.TranscribeListView.as_view()),

The base APIViewMixin implements a base implementation of serialize_object which
uses the generic django.forms.models.model_to_dict and can be overridden as needed.
"""

from django.forms.models import model_to_dict
from django.http import JsonResponse
from django.views.generic import DetailView, ListView
from django.views.generic.base import TemplateResponseMixin
from django.core.serializers.json import DjangoJSONEncoder


class URLAwareEncoder(DjangoJSONEncoder):
    """
    JSON encoder subclass which handles things like ImageFieldFile which define
    a url property
    """

    def default(self, obj):
        if hasattr(obj, "url"):
            return obj.url
        else:
            return super().default(obj)


class APIViewMixin(TemplateResponseMixin):
    """
    TemplateResponseMixin subclass which will optionally render a JSON view of
    the context data when the URL path ends in .json or the querystring has
    "format=json"
    """

    def render_to_response(self, context, **response_kwargs):
        # This could also parse Accept headers if we wanted to take on the
        # support overhead of content-negotiation:
        req = self.request
        if req.path.endswith(".json") or req.GET.get("format") == "json":
            return self.render_to_json_response(context)
        else:
            return super().render_to_response(context, **response_kwargs)

    def render_to_json_response(self, context):
        data = self.serialize_object(context["object"])
        return JsonResponse(data, encoder=URLAwareEncoder)

    def serialize_object(self, obj):
        data = model_to_dict(obj)
        if hasattr(obj, "get_absolute_url"):
            data["url"] = self.request.build_absolute_uri(
                "%s?format=json" % obj.get_absolute_url()
            )
        return data


class APIDetailView(APIViewMixin, DetailView):
    """DetailView which can also return JSON"""


class APIListView(APIViewMixin, ListView):
    """ListView which can also return JSON with consistent pagination"""

    def render_to_json_response(self, context):
        data = {"objects": [self.serialize_object(i) for i in context["object_list"]]}

        page_obj = context["page_obj"]
        if page_obj:
            data["pagination"] = pagination = {
                "first": self.request.build_absolute_uri(
                    "%s?page=%s" % (self.request.path, 1)
                ),
                "last": self.request.build_absolute_uri(
                    "%s?page=%s" % (self.request.path, page_obj.paginator.num_pages)
                ),
            }
            if page_obj.has_next():
                pagination["next"] = self.request.build_absolute_uri(
                    "%s?page=%s" % (self.request.path, page_obj.next_page_number())
                )

        return JsonResponse(data, encoder=URLAwareEncoder)
