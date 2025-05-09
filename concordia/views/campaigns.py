from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from concordia.api_views import APIDetailView, APIListView
from concordia.models import (
    STATUS_COUNT_KEYS,
    Asset,
    Campaign,
    ResearchCenter,
    SiteReport,
    Topic,
    Transcription,
    TranscriptionStatus,
)

from .decorators import default_cache_control, user_cache_control
from .utils import (
    ASSETS_PER_PAGE,
    annotate_children_with_progress_stats,
    calculate_asset_stats,
)


@method_decorator(default_cache_control, name="dispatch")
class CampaignListView(APIListView):
    template_name = "transcriptions/campaign_list.html"

    queryset = (
        Campaign.objects.published()
        .listed()
        .filter(status=Campaign.Status.ACTIVE)
        .order_by("ordering", "title")
    )
    context_object_name = "campaigns"

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data["topics"] = (
            Topic.objects.published().listed().order_by("ordering", "title")
        )
        data["completed_campaigns"] = (
            Campaign.objects.published()
            .listed()
            .filter(status__in=[Campaign.Status.COMPLETED, Campaign.Status.RETIRED])
            .order_by("ordering", "title")
        )
        return data

    def serialize_context(self, context):
        data = super().serialize_context(context)

        object_list = data["objects"]

        campaign_stats_qs = (
            Campaign.objects.filter(pk__in=[i["id"] for i in object_list])
            .annotate(
                **{
                    v: Count(
                        "project__item__asset",
                        filter=Q(
                            project__published=True,
                            project__item__published=True,
                            project__item__asset__published=True,
                            project__item__asset__transcription_status=k,
                        ),
                    )
                    for k, v in STATUS_COUNT_KEYS.items()
                }
            )
            .values("pk", *STATUS_COUNT_KEYS.values())
        )

        campaign_asset_counts = {}
        for campaign_stats in campaign_stats_qs:
            campaign_asset_counts[campaign_stats.pop("pk")] = campaign_stats

        for obj in object_list:
            obj["asset_stats"] = campaign_asset_counts[obj["id"]]

        return data


@method_decorator(default_cache_control, name="dispatch")
class CompletedCampaignListView(APIListView):
    model = Campaign
    template_name = "transcriptions/campaign_list_small_blocks.html"
    context_object_name = "campaigns"

    def _get_all_campaigns(self):
        campaignType = self.request.GET.get("type", None)
        campaigns = Campaign.objects.published().listed()
        if campaignType is None:
            return campaigns.filter(
                status__in=[Campaign.Status.COMPLETED, Campaign.Status.RETIRED]
            )
        elif campaignType == "retired":
            status = Campaign.Status.RETIRED
        else:
            status = Campaign.Status.COMPLETED

        return campaigns.filter(status=status)

    def get_queryset(self):
        campaigns = self._get_all_campaigns()
        research_center = self.request.GET.get("research_center", None)
        if research_center is not None:
            campaigns = campaigns.filter(research_centers=research_center)
        return campaigns.order_by("-completed_date")

    def get_context_data(self, **kwargs):
        campaigns = self._get_all_campaigns()
        data = super().get_context_data(**kwargs)
        data["result_count"] = self.object_list.count()
        data["research_centers"] = ResearchCenter.objects.filter(
            campaign__in=campaigns
        ).distinct()

        return data


@method_decorator(default_cache_control, name="dispatch")
class CampaignTopicListView(TemplateView):
    template_name = "transcriptions/campaign_topic_list.html"

    def get(self, context):
        data = {}
        data["campaigns"] = (
            Campaign.objects.published()
            .listed()
            .filter(status=Campaign.Status.ACTIVE)
            .annotated()
            .order_by("ordering", "title")
        )
        data["topics"] = (
            Topic.objects.published().listed().order_by("ordering", "title")[:5]
        )
        data["completed_campaigns"] = (
            Campaign.objects.published()
            .listed()
            .filter(status__in=[Campaign.Status.COMPLETED, Campaign.Status.RETIRED])
            .order_by("ordering", "title")
        )

        return render(self.request, self.template_name, data)


@method_decorator(default_cache_control, name="dispatch")
class CampaignDetailView(APIDetailView):
    template_name = "transcriptions/campaign_detail.html"
    completed_template_name = "transcriptions/campaign_detail_completed.html"
    retired_template_name = "transcriptions/campaign_detail_retired.html"
    context_object_name = "campaign"
    queryset = Campaign.objects.published().order_by("title")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.object and self.object.status == Campaign.Status.RETIRED:
            latest_report = SiteReport.objects.filter(campaign=ctx["campaign"]).latest(
                "created_on"
            )
            ctx["completed_count"] = latest_report.assets_completed
            ctx["contributor_count"] = latest_report.registered_contributors
        else:
            projects = (
                ctx["campaign"].project_set.published().order_by("ordering", "title")
            )
            ctx["filters"] = filters = {}
            filter_by_reviewable = kwargs.get("filter_by_reviewable", False)
            if filter_by_reviewable:
                projects = projects.filter(
                    item__asset__transcription__id__in=Transcription.objects.exclude(
                        user=self.request.user.id
                    ).values_list("id", flat=True)
                )
                ctx["filter_assets"] = True
            projects = projects.annotate(
                **{
                    f"{key}_count": Count(
                        "item__asset",
                        filter=Q(
                            item__published=True,
                            item__asset__published=True,
                            item__asset__transcription_status=key,
                        ),
                    )
                    for key in TranscriptionStatus.CHOICE_MAP
                }
            )

            if filter_by_reviewable:
                status = TranscriptionStatus.SUBMITTED
            else:
                status = self.request.GET.get("transcription_status")
            if status in TranscriptionStatus.CHOICE_MAP:
                projects = projects.exclude(**{f"{status}_count": 0})
                # We only want to pass specific QS parameters
                # to lower-level search pages:
                filters["transcription_status"] = status
            ctx["sublevel_querystring"] = urlencode(filters)

            annotate_children_with_progress_stats(projects)
            ctx["projects"] = projects

            campaign_assets = Asset.objects.filter(
                item__project__campaign=self.object,
                item__project__published=True,
                item__published=True,
                published=True,
            )
            if filter_by_reviewable:
                campaign_assets = campaign_assets.exclude(
                    transcription__user=self.request.user.id
                )
                ctx["transcription_status"] = TranscriptionStatus.SUBMITTED
            else:
                ctx["transcription_status"] = status

            calculate_asset_stats(campaign_assets, ctx)

        return ctx

    def serialize_context(self, context):
        ctx = super().serialize_context(context)
        ctx["object"]["related_links"] = [
            {"title": title, "url": url}
            for title, url in self.object.resource_set.values_list(
                "title", "resource_url"
            )
        ]
        return ctx

    def get_template_names(self):
        if self.object.status == Campaign.Status.COMPLETED:
            return [self.completed_template_name]
        elif self.object.status == Campaign.Status.RETIRED:
            return [self.retired_template_name]
        return super().get_template_names()


@method_decorator(user_cache_control, name="dispatch")
class FilteredCampaignDetailView(CampaignDetailView):
    def get_context_data(self, **kwargs):
        if self.request.user.is_authenticated and self.request.user.is_staff:
            kwargs["filter_by_reviewable"] = True

        return super().get_context_data(**kwargs)


@method_decorator(default_cache_control, name="dispatch")
class ReportCampaignView(TemplateView):
    """
    Report about campaign resources and status
    """

    template_name = "transcriptions/campaign_report.html"

    def get(self, request, campaign_slug):
        campaign = get_object_or_404(Campaign.objects.published(), slug=campaign_slug)

        try:
            page = int(self.request.GET.get("page", "1"))
        except ValueError:
            page = 1

        campaign_assets = Asset.objects.published().filter(
            item__project__campaign=campaign
        )

        ctx = {
            "title": campaign.title,
            "campaign_slug": campaign.slug,
            "total_asset_count": campaign_assets.count(),
        }

        projects_qs = campaign.project_set.published().order_by("title")

        projects_qs = projects_qs.annotate(
            asset_count=Count(
                "item__asset",
                filter=Q(item__published=True, item__asset__published=True),
                distinct=True,
            )
        )
        projects_qs = projects_qs.annotate(
            tag_count=Count("item__asset__userassettagcollection__tags", distinct=True)
        )
        projects_qs = projects_qs.annotate(
            transcriber_count=Count("item__asset__transcription__user", distinct=True),
            reviewer_count=Count(
                "item__asset__transcription__reviewed_by", distinct=True
            ),
        )

        paginator = Paginator(projects_qs, ASSETS_PER_PAGE)
        if page > paginator.num_pages:
            page = 1
        projects_page = paginator.get_page(page)

        self.add_transcription_status_summary_to_projects(projects_page)

        ctx["paginator"] = paginator
        ctx["projects"] = projects_page

        return render(self.request, self.template_name, ctx)

    def add_transcription_status_summary_to_projects(self, projects):
        status_qs = Asset.objects.filter(
            item__published=True, item__project__in=projects, published=True
        )
        status_qs = status_qs.values_list("item__project__id", "transcription_status")
        status_qs = status_qs.annotate(Count("transcription_status"))
        project_statuses = {}

        for project_id, status_value, count in status_qs:
            status_name = TranscriptionStatus.CHOICE_MAP[status_value]
            project_statuses.setdefault(project_id, []).append((status_name, count))

        # We'll sort the statuses in the same order they're presented in the choices
        # list so the display order will be both stable and consistent with the way
        # we talk about the workflow:
        sort_order = [j for i, j in TranscriptionStatus.CHOICES]

        for project in projects:
            statuses = project_statuses.get(project.id, [])
            statuses.sort(key=lambda i: sort_order.index(i[0]))
            project.transcription_statuses = statuses
