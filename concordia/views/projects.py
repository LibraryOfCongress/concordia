from urllib.parse import urlencode

from django.db.models import Count, Q, QuerySet
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator

from concordia.api_views import APIListView
from concordia.models import Asset, Campaign, Project, TranscriptionStatus

from .decorators import default_cache_control, user_cache_control
from .utils import annotate_children_with_progress_stats, calculate_asset_stats


@method_decorator(default_cache_control, name="dispatch")
class ProjectDetailView(APIListView):
    """
    Display a paginated list of items for a single project.

    Handles GET requests for a published project scoped by campaign and project
    slugs. Applies optional filtering to show only items with a specific
    transcription status. Builds context including campaign/project metadata
    and progress statistics.

    Attributes:
        template_name (str): Template used for project detail.
        context_object_name (str): Context key under which the list of items is
            exposed to templates.
        paginate_by (int): Number of items per page.

    Returns:
        HttpResponse: Rendered project detail page or a redirect if the project
            or campaign cannot be found.
    """

    template_name = "transcriptions/project_detail.html"
    context_object_name = "items"
    paginate_by = 10

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """
        Dispatch the request or redirect to campaign if the item is missing.

        If an `Http404` occurs during normal dispatch (e.g., item not found),
        redirect to the campaign page to keep navigation stable.

        Args:
            request (HttpRequest): The incoming request.
            *args: Positional args forwarded to the superclass.
            **kwargs: Keyword args forwarded to the superclass.

        Returns:
            HttpResponse: Normal response from `APIListView.dispatch` or a
                redirect to the campaign page when the asset path is invalid.
        """
        try:
            return super().dispatch(request, *args, **kwargs)
        except Http404:
            campaign = get_object_or_404(
                Campaign.objects.published(), slug=self.kwargs["campaign_slug"]
            )
            return redirect(campaign)

    def get_queryset(self, filter_by_reviewable: bool = False) -> QuerySet:
        """
        Return the queryset of items for the current project.

        Loads the published project identified by `campaign_slug` and `slug`,
        then builds an ordered queryset of its published items. When
        `filter_by_reviewable` is true, excludes items already transcribed by
        the requesting user. Each item is annotated with per-status counts
        using `TranscriptionStatus.CHOICE_MAP`.

        Request Parameters:
            - `transcription_status` (str, optional): If present and valid,
              restrict the queryset to items that have at least one asset in
              that status (items with zero count for that status are excluded).

        Args:
            filter_by_reviewable (bool): If true, exclude items containing an
                asset with a transcription by the current user.

        Returns:
            QuerySet: Ordered queryset of items annotated with per-status
                counts. Also sets `self.filters` to the propagated filters that
                should appear in sublevel navigation links.
        """
        self.project = get_object_or_404(
            Project.objects.published().select_related("campaign"),
            slug=self.kwargs["slug"],
            campaign__slug=self.kwargs["campaign_slug"],
        )

        item_qs = self.project.item_set.published().order_by("item_id")
        if filter_by_reviewable:
            item_qs = item_qs.exclude(asset__transcription__user=self.request.user.id)
        item_qs = item_qs.annotate(
            **{
                f"{key}_count": Count(
                    "asset", filter=Q(asset__transcription_status=key)
                )
                for key in TranscriptionStatus.CHOICE_MAP
            }
        )

        self.filters: dict[str, str] = {}

        if filter_by_reviewable:
            status = TranscriptionStatus.SUBMITTED
        else:
            status = self.request.GET.get("transcription_status")
        if status in TranscriptionStatus.CHOICE_MAP:
            item_qs = item_qs.exclude(**{f"{status}_count": 0})
            # We only want to pass specific QS parameters to lower-level search
            # pages so we'll record those here:
            self.filters["transcription_status"] = status

        return item_qs

    def get_context_data(self, **kws) -> dict[str, object]:
        """
        Build context for the project detail template.

        Context Format:
            - `items` (QuerySet): Paginated list of project items.
            - `project` (Project): The current project.
            - `campaign` (Campaign): The parent campaign.
            - `filters` (dict[str, str] | absent): Filters applied to this view.
            - `sublevel_querystring` (str | absent): URL-encoded filters to pass
              into sublevel pages.
            - `transcription_status` (str | None): Current status filter or
              derived status when reviewable filtering is active.
            - `filter_assets` (bool | absent): True when items are filtered to
              exclude those transcribed by the current user.
            - `total_assets` (int): Count of assets in the project (published).
            - `completed_assets` (int): Count of completed assets.
            - `in_progress_assets` (int): Count of in-progress assets.
            - `not_started_assets` (int): Count of not-started assets.
            - `submitted_assets` (int): Count of submitted assets.
            - Progress statistics on each item are added in-place by
              `annotate_children_with_progress_stats`.

        Args:
            **kws: Optional flags. Recognized:
                - `filter_by_reviewable` (bool): When true, limit assets and
                  force `transcription_status` to `SUBMITTED`.

        Returns:
            dict[str, object]: Template context including project/campaign
                metadata, filters, and computed statistics.
        """
        ctx = super().get_context_data(**kws)
        ctx["project"] = project = self.project
        ctx["campaign"] = project.campaign

        if self.filters:
            ctx["sublevel_querystring"] = urlencode(self.filters)
            ctx["filters"] = self.filters

        project_assets = Asset.objects.filter(
            item__project=project, published=True, item__published=True
        )
        filter_by_reviewable = kws.get("filter_by_reviewable", False)
        if filter_by_reviewable:
            project_assets = project_assets.exclude(
                transcription__user=self.request.user.id
            )
            ctx["filter_assets"] = True
            ctx["transcription_status"] = TranscriptionStatus.SUBMITTED
        else:
            ctx["transcription_status"] = self.request.GET.get("transcription_status")

        calculate_asset_stats(project_assets, ctx)

        annotate_children_with_progress_stats(ctx["items"])

        return ctx

    def serialize_context(self, context: dict[str, object]) -> dict[str, object]:
        """
        Serialize context for API responses.

        Extends the base list serialization by attaching the serialized project
        object. Mirrors the behavior used elsewhere to pair list payloads with
        their parent container.

        Args:
            context (dict[str, object]): The view context to serialize.

        Returns:
            dict[str, object]: A JSON-serializable structure including:
                - `results`/pagination fields from the base serializer.
                - `project` (dict): Serialized project metadata.
        """
        data = super().serialize_context(context)
        data["project"] = self.serialize_object(context["project"])
        return data


@method_decorator(user_cache_control, name="dispatch")
class FilteredProjectDetailView(ProjectDetailView):
    """
    Project detail view that filters to reviewable items for the user.

    This variant restricts the queryset and context to prioritize items that
    are ready for review by the current user (i.e., excludes items with assets
    already transcribed by that user). It also sets the effective status filter
    to `SUBMITTED` in context.
    """

    def get_queryset(self) -> QuerySet:
        """
        Return the review-focused queryset.

        Delegates to the parent implementation with `filter_by_reviewable=True`.

        Returns:
            QuerySet: Item queryset annotated with status counts and filtered
                for reviewable content.
        """
        return super().get_queryset(filter_by_reviewable=True)

    def get_context_data(self, **kws) -> dict[str, object]:
        """
        Build context with reviewable filtering enabled.

        Sets the `filter_by_reviewable` flag before delegating to the parent
        implementation so that downstream context keys (e.g., status and
        `filter_assets`) reflect review-mode behavior.

        Args:
            **kws: Context keyword arguments.

        Returns:
            dict[str, object]: Context dictionary with reviewable filtering.
        """
        kws["filter_by_reviewable"] = True

        return super().get_context_data(**kws)
