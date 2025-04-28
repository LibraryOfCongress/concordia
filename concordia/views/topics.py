from urllib.parse import urlencode

from django.db.models import Count, Prefetch, Q

from concordia.api_views import APIDetailView
from concordia.models import Asset, ProjectTopic, Topic, TranscriptionStatus

from .utils import annotate_children_with_progress_stats, calculate_asset_stats


# @method_decorator(default_cache_control, name="dispatch")
# @method_decorator(cache_page(60 * 60, cache="view_cache"), name="dispatch")
class TopicDetailView(APIDetailView):
    template_name = "transcriptions/topic_detail.html"
    context_object_name = "topic"
    queryset = Topic.objects.published().order_by("title")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        projects = (
            ctx["topic"]
            .project_set.published()
            .annotate(
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
            # Prefetch the ProjectTopic link for this topic onto each project
            # so we can access the url_filter without extra queries
            .prefetch_related(
                Prefetch(
                    "projecttopic_set",
                    queryset=ProjectTopic.objects.filter(topic=ctx["topic"]),
                    to_attr="topic_links",
                )
            )
            .order_by("campaign", "ordering", "title")
        )

        # Attach the url_filter, if any, to the project itself to access in the template
        for project in projects:
            if project.topic_links:
                project.url_filter = project.topic_links[0].url_filter
            else:
                project.url_filter = None

        ctx["filters"] = filters = {}
        status = self.request.GET.get("transcription_status")
        if status in TranscriptionStatus.CHOICE_MAP:
            projects = projects.exclude(**{f"{status}_count": 0})
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
