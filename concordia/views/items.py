from urllib.parse import urlencode

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator

from concordia.api_views import APIListView
from concordia.models import Campaign, Item, TranscriptionStatus
from concordia.utils import get_image_urls_from_asset

from .decorators import default_cache_control, user_cache_control
from .utils import calculate_asset_stats


@method_decorator(default_cache_control, name="dispatch")
class ItemDetailView(APIListView):
    """
    Handle GET requests on /campaign/<campaign>/<project>/<item>

    This uses a ListView to paginate the item's assets
    """

    template_name = "transcriptions/item_detail.html"
    context_object_name = "assets"
    paginate_by = 10

    http_method_names = ["get", "options", "head"]

    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except Http404:
            campaign = get_object_or_404(
                Campaign.objects.published(), slug=self.kwargs["campaign_slug"]
            )
            return redirect(campaign)

    def _get_assets(self):
        assets = self.item.asset_set.published()
        if self.kwargs.get("filter_by_reviewable", False):
            assets = assets.exclude(transcription__user=self.request.user.id)
        return assets

    def get_queryset(self):
        self.item = get_object_or_404(
            Item.objects.published().select_related("project__campaign"),
            project__campaign__slug=self.kwargs["campaign_slug"],
            project__slug=self.kwargs["project_slug"],
            item_id=self.kwargs["item_id"],
        )

        asset_qs = self._get_assets().order_by("sequence")
        asset_qs = asset_qs.select_related(
            "item__project__campaign", "item__project", "item"
        )

        self.filters = {}
        if self.kwargs.get("filter_by_reviewable", False):
            status = TranscriptionStatus.SUBMITTED
        else:
            status = self.request.GET.get("transcription_status")
        if status in TranscriptionStatus.CHOICE_MAP:
            asset_qs = asset_qs.filter(transcription_status=status)
            # We only want to pass specific QS parameters to lower-level search
            # pages so we'll record those here:
            self.filters["transcription_status"] = status

        return asset_qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        ctx.update(
            {
                "campaign": self.item.project.campaign,
                "project": self.item.project,
                "item": self.item,
                "sublevel_querystring": urlencode(self.filters),
                "filters": self.filters,
            }
        )

        item_assets = self._get_assets()
        if self.kwargs.get("filter_by_reviewable", False):
            ctx["filter_assets"] = True
            ctx["transcription_status"] = TranscriptionStatus.SUBMITTED
        else:
            ctx["transcription_status"] = self.request.GET.get("transcription_status")

        calculate_asset_stats(item_assets, ctx)

        return ctx

    def serialize_context(self, context):
        data = super().serialize_context(context)

        for i, asset in enumerate(context["object_list"]):
            serialized_asset = data["objects"][i]
            image_url, thumbnail_url = get_image_urls_from_asset(asset)
            serialized_asset["image_url"] = image_url
            serialized_asset["thumbnail_url"] = thumbnail_url

        data["item"] = self.serialize_object(context["item"])
        return data


@method_decorator(user_cache_control, name="dispatch")
class FilteredItemDetailView(ItemDetailView):
    def get_queryset(self):
        self.kwargs["filter_by_reviewable"] = True
        return super().get_queryset()

    def get_context_data(self, **kwargs):
        self.kwargs["filter_by_reviewable"] = True
        kwargs["filter_by_reviewable"] = True
        return super().get_context_data(**kwargs)
