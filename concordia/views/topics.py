from typing import Any
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
    """
    Display a topic and its projects with aggregated progress stats.

    Renders the topic detail page with a list of published projects tied to
    the topic, annotated with per-status asset counts. Supports an optional
    transcription-status filter which narrows projects to those containing
    assets in that status and respects per-topic URL filter overrides.

    Attributes:
        template_name (str): Template used for topic detail.
        context_object_name (str): Context key for the main object (`topic`).
        queryset (QuerySet[Topic]): Base queryset for lookup and ordering.
    """

    template_name = "transcriptions/topic_detail.html"
    context_object_name = "topic"
    queryset = Topic.objects.published().order_by("title")

    def get_context_data(self, **kwargs: Any) -> dict[str, object]:
        """
        Build context for the topic detail template.

        Computes project-level progress annotations and applies an optional
        status filter. Also computes topic-wide asset statistics and prepares
        sublevel querystring parameters for downstream pages.

        Request Parameters:
            - `transcription_status` (str, optional): When present and valid,
              filters projects to those that:
                * have at least one asset in the given status, and
                * either have no `pt__url_filter` or have one matching the
                  requested status.

        Context Format:
            - `topic` (Topic): The topic being viewed.
            - `projects` (QuerySet): Topic projects with:
                * per-status counts (e.g., `submitted_count`), and
                * `topic_ordering` and `topic_url_filter` from the through
                  relation.
            - `filters` (dict[str, str]): Applied filter parameters.
            - `sublevel_querystring` (str): URL-encoded `filters` for links.
            - `transcription_status` (str | None): Reflected status filter.
            - Aggregated asset stats for the topic (added by
              `calculate_asset_stats`), including keys such as:
                * `total_assets`, `completed_assets`, `in_progress_assets`,
                  `not_started_assets`, `submitted_assets`.

        Args:
            **kwargs: Additional context arguments passed by the base class.

        Returns:
            dict[str, object]: Context for rendering the topic detail page.
        """
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

    def serialize_context(self, context: dict[str, object]) -> dict[str, object]:
        """
        Serialize context for API consumers.

        Extends the base serializer with a `related_links` list derived from the
        topic's associated resources.

        Args:
            context (dict[str, object]): Fully built template context.

        Returns:
            dict[str, object]: JSON-serializable payload that includes the base
                fields from `APIDetailView.serialize_context` and:
                - `object.related_links` (list[dict]): Each with:
                    * `title` (str)
                    * `url` (str)
        """
        ctx = super().serialize_context(context)
        ctx["object"]["related_links"] = [
            {"title": title, "url": url}
            for title, url, sequence in self.object.resource_set.values_list(
                "title", "resource_url"
            )
        ]
        return ctx
