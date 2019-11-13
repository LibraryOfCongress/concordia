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
from time import time

from django.core.serializers.json import DjangoJSONEncoder
from django.forms.models import model_to_dict
from django.http import JsonResponse
from django.views.generic import DetailView, ListView
from django.views.generic.base import TemplateResponseMixin


class URLAwareEncoder(DjangoJSONEncoder):
    """
    JSON encoder subclass which handles things like ImageFieldFile which define
    a url property
    """

    def default(self, obj):
        if not obj:
            # Beyond the obvious, this handles the case where FileFields and
            # their subclasses (e.g. ImageField) define a url property which
            # will raise ValueError if accessed when the name property is empty.
            return None
        elif hasattr(obj, "url"):
            return obj.url
        elif hasattr(obj, "get_absolute_url"):
            return obj.get_absolute_url()
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
        data = self.serialize_context(context)
        self.make_absolute_urls(data)
        return JsonResponse(data, encoder=URLAwareEncoder)

    def serialize_context(self, context):
        # Subclasses will want to selectively filter this but we
        # will simply return the context verbatim:
        return context

    def serialize_object(self, obj):
        data = model_to_dict(obj)
        if hasattr(obj, "get_absolute_url"):
            data["url"] = obj.get_absolute_url()
        return data

    def make_absolute_urls(self, data):
        if isinstance(data, dict):
            for k, v in data.items():
                if k.endswith("url") and isinstance(v, str) and v.startswith("/"):
                    data[k] = self.request.build_absolute_uri(v)
                elif isinstance(v, (dict, list)):
                    self.make_absolute_urls(v)
        elif isinstance(data, list):
            for i in data:
                self.make_absolute_urls(i)


class APIDetailView(APIViewMixin, DetailView):
    """DetailView which can also return JSON"""

    def serialize_context(self, context):
        return {"object": self.serialize_object(context["object"])}


class APIListView(APIViewMixin, ListView):
    """ListView which can also return JSON with consistent pagination"""

    def render_to_response(self, context, **response_kwargs):
        page_obj = context["page_obj"]

        if page_obj:
            per_page = context["paginator"].per_page

            context["pagination"] = pagination = {
                "first": self.build_url_for_page(1, per_page),
                "last": self.build_url_for_page(page_obj.paginator.num_pages, per_page),
            }
            if page_obj.has_next():
                pagination["next"] = self.build_url_for_page(
                    page_obj.next_page_number(), per_page
                )

        response = super().render_to_response(context, **response_kwargs)

        if "pagination" in context:
            response["Link"] = ", ".join(
                f'<{url}>; rel="{rel}"' for rel, url in pagination.items()
            )

        return response

    def build_url_for_page(self, page_number, per_page):
        qs = self.request.GET.copy()
        qs["page"] = page_number
        qs["per_page"] = per_page
        return self.request.build_absolute_uri(
            "%s?%s" % (self.request.path, qs.urlencode())
        )

    def get_paginate_by(self, queryset):
        per_page = self.request.GET.get("per_page")

        if per_page and per_page.isdigit():
            return int(per_page)
        else:
            return self.paginate_by

    def serialize_context(self, context):
        data = {
            "objects": [self.serialize_object(i) for i in context["object_list"]],
            "sent": time(),
        }

        if "pagination" in context:
            data["pagination"] = context["pagination"]

        return data
