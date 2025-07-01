from urllib.parse import urlencode

from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator

from concordia.api_views import APIListView
from concordia.models import Asset, Campaign, Project, TranscriptionStatus

from .decorators import default_cache_control, user_cache_control
from .utils import annotate_children_with_progress_stats, calculate_asset_stats


@method_decorator(default_cache_control, name="dispatch")
class ProjectDetailView(APIListView):
    template_name = "transcriptions/project_detail.html"
    context_object_name = "items"
    paginate_by = 10

    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except Http404:
            campaign = get_object_or_404(
                Campaign.objects.published(), slug=self.kwargs["campaign_slug"]
            )
            return redirect(campaign)

    def get_queryset(self, filter_by_reviewable=False):
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

        self.filters = {}

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

    def get_context_data(self, **kws):
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

    def serialize_context(self, context):
        data = super().serialize_context(context)
        data["project"] = self.serialize_object(context["project"])
        return data


@method_decorator(user_cache_control, name="dispatch")
class FilteredProjectDetailView(ProjectDetailView):
    def get_queryset(self):
        return super().get_queryset(filter_by_reviewable=True)

    def get_context_data(self, **kws):
        kws["filter_by_reviewable"] = True

        return super().get_context_data(**kws)
