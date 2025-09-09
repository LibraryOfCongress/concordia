from urllib.parse import urlencode

from django.db.models import QuerySet
from django.http import Http404, HttpRequest, HttpResponse
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
    Display a paginated list of assets for a specific item.

    This view handles GET requests and renders the item detail page,
    which includes the item's assets, context for filtering, and transcription stats.

    Uses `APIListView` to support both HTML rendering and optional JSON output for
    frontend consumption.

    Attributes:
        template_name (str): Template used to render the asset list.
        context_object_name (str): The variable name for assets in the template.
        paginate_by (int): Number of assets to display per page.
        http_method_names (list[str]): HTTP methods supported by the view.
    """

    template_name = "transcriptions/item_detail.html"
    context_object_name = "assets"
    paginate_by = 10

    http_method_names = ["get", "options", "head"]

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """
        Handle incoming HTTP requests and redirect if the item or campaign is missing.

        Args:
            request (HttpRequest): The HTTP request object.

        Returns:
            HttpResponse: The response for the view or a redirect to the campaign page.
        """
        try:
            return super().dispatch(request, *args, **kwargs)
        except Http404:
            campaign = get_object_or_404(
                Campaign.objects.published(), slug=self.kwargs["campaign_slug"]
            )
            return redirect(campaign)

    def _get_assets(self) -> QuerySet:
        """
        Retrieve the queryset of published assets for the current item.

        If the `filter_by_reviewable` flag is set in `self.kwargs`, excludes any assets
        already transcribed by the current user to allow for review filtering.

        Returns:
            QuerySet: The filtered set of published `Asset` objects for the item.
        """
        assets = self.item.asset_set.published()
        if self.kwargs.get("filter_by_reviewable", False):
            assets = assets.exclude(transcription__user=self.request.user.id)
        return assets

    def get_queryset(self):
        """
        Build and return the queryset of assets for the current item.

        Retrieves the specified `Item` and filters its published assets based on
        transcription status. If `filter_by_reviewable` is set in `self.kwargs`,
        filters assets not yet transcribed by the current user and restricts the
        status to SUBMITTED.

        The resulting queryset is ordered by sequence and annotated for use in the view.
        Also sets `self.filters` for use in context and querystring construction.

        Returns:
            QuerySet: The filtered and ordered queryset of `Asset` objects.
        """
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
        """
        Construct the context dictionary for rendering the item detail page.

        Adds campaign, project, item and transcription status to the context. Also
        attaches filter state and querystring for pagination or navigation. If review
        filtering is enabled, the context is marked accordingly.

        Includes asset-level transcription statistics via `calculate_asset_stats()`.

        Returns:
            dict: The context data for the template rendering.
        """
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

    def serialize_context(self, context: dict) -> dict:
        """
        Serialize the context data for JSON responses.

        Enhances each serialized asset with its associated image and thumbnail URLs.
        Also includes serialized data for the parent item.

        Args:
            context (dict): The original context data returned by `get_context_data()`.

        Returns:
            dict: The serialized version of the context suitable for API responses.
        """
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
    """
    View that displays only reviewable assets for an item.

    Inherits from `ItemDetailView` but overrides queryset and context behavior to
    exclude assets already transcribed by the current user. Used to present assets
    eligible for review.
    """

    def get_queryset(self):
        """
        Modify the queryset to include only reviewable assets.

        Sets the `filter_by_reviewable` flag in `self.kwargs` to enable filtering logic
        in the parent view.

        Returns:
            QuerySet: A filtered queryset of `Asset` objects for review.
        """
        self.kwargs["filter_by_reviewable"] = True
        return super().get_queryset()

    def get_context_data(self, **kwargs):
        """
        Update the context to reflect that only reviewable assets are being shown.

        Ensures `filter_by_reviewable` is set in both `self.kwargs` and `kwargs` so that
        downstream logic (like filtering and labeling) behaves consistently.

        Returns:
            dict: The context dictionary for rendering the filtered item detail view.
        """
        self.kwargs["filter_by_reviewable"] = True
        kwargs["filter_by_reviewable"] = True
        return super().get_context_data(**kwargs)
