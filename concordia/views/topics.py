from urllib.parse import urlencode

from django.db.models import Count, F, FilteredRelation, Q
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

from concordia.api_views import APIDetailView
from concordia.models import Asset, Topic, TranscriptionStatus

from .decorators import default_cache_control
from .utils import annotate_children_with_progress_stats, calculate_asset_stats


@method_decorator(default_cache_control, name="dispatch")
@method_decorator(cache_page(60 * 60, cache="view_cache"), name="dispatch")
class TopicDetailView(APIDetailView):
    template_name = "transcriptions/topic_detail.html"
    context_object_name = "topic"
    queryset = Topic.objects.published().order_by("title")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        topic = ctx["topic"]

        status = self.request.GET.get("transcription_status")
        status_valid = status in TranscriptionStatus.CHOICE_MAP

        projects = (
            topic.project_set.published().annotate(
                **{
                    f"{key}_count": Count(
                        "item__asset",
                        filter=Q(
                            item__published=True,
                            item__asset__published=True,
                            item__asset__transcription_status=key,
                        ),
                    )
                    for key in TranscriptionStatus.CHOICE_MAP.keys()
                }
            )
            # Pin the through relation to THIS topic, otherwise it will annotate for
            # each ProjectTopic the project is part of
            .annotate(
                pt=FilteredRelation(
                    "projecttopic", condition=Q(projecttopic__topic=topic)
                )
            )
            # Pull fields from the pinned alias
            .annotate(
                topic_ordering=F("pt__ordering"),
                topic_url_filter=F("pt__url_filter"),
            )
        )

        # If there's a status filter, we want to exclude any projects
        # don't don't have assets in that status, as well as any
        # that have a URL filter that's different than the status filter
        if status_valid:
            ctx["transcription_status"] = status
            projects = projects.filter(
                Q(pt__url_filter__isnull=True)
                | Q(pt__url_filter="")
                | Q(pt__url_filter=status)
            ).exclude(**{f"{status}_count": 0})

        projects = projects.order_by("topic_ordering", "campaign__title", "title")

        ctx["filters"] = filters = {}
        if status_valid:
            # We only want to pass specific QS parameters to lower-level search pages:
            filters["transcription_status"] = status
        ctx["sublevel_querystring"] = urlencode(filters)

        annotate_children_with_progress_stats(projects)
        ctx["projects"] = projects

        topic_assets = Asset.objects.filter(
            item__project__topics=self.object,
            item__project__published=True,
            item__published=True,
            published=True,
        )

        calculate_asset_stats(topic_assets, ctx)

        return ctx

    def serialize_context(self, context):
        ctx = super().serialize_context(context)
        ctx["object"]["related_links"] = [
            {"title": title, "url": url}
            for title, url, sequence in self.object.resource_set.values_list(
                "title", "resource_url"
            )
        ]
        return ctx
