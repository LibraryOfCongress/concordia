from django.contrib import admin, messages
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.db.models import Count, F, Max, Q, QuerySet
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from concordia.admin.filters import (
    CampaignListFilter,
    CampaignProjectListFilter,
    NullableTimestampFilter,
)
from concordia.models import Campaign
from importer.tasks.assets import download_asset_task

from .models import (
    DownloadAssetImageJob,
    ImportItem,
    ImportItemAsset,
    ImportJob,
    VerifyAssetImageJob,
)


@admin.action(description="Retry import")
def retry_download_task(
    modeladmin: admin.ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet[ImportItemAsset],
) -> None:
    """
    Queue the asset download Celery task again for selected rows.

    Args:
        modeladmin (admin.ModelAdmin): Admin class invoking the action.
        request (HttpRequest): Current admin request.
        queryset (QuerySet[ImportItemAsset]): Selected ImportItemAsset rows.

    Returns:
        None
    """
    pks = queryset.values_list("pk", flat=True)
    for pk in pks:
        download_asset_task.delay(pk)
    messages.add_message(request, messages.INFO, "Queued %d tasks" % len(pks))


class LastStartedFilter(NullableTimestampFilter):
    """Filter by whether a task has a 'last_started' timestamp."""

    title = "Last Started"
    parameter_name = "last_started"
    lookup_labels = ("Unstarted", "Started")


class CompletedFilter(NullableTimestampFilter):
    """Filter by whether a task has a 'completed' timestamp."""

    title = "Completed"
    parameter_name = "completed"
    lookup_labels = ("Incomplete", "Completed")


class FailedFilter(NullableTimestampFilter):
    """Filter by whether a task has a 'failed' timestamp."""

    title = "Failed"
    parameter_name = "failed"
    lookup_labels = ("Has not failed", "Has failed")


class ImportJobProjectListFilter(CampaignProjectListFilter):
    """Project filter for ImportJob rows."""

    parameter_name = "project__in"
    related_filter_parameter = "project__campaign__id__exact"
    project_ref = "project_id"


class ImportJobItemProjectListFilter(CampaignProjectListFilter):
    """Project filter for ImportItem rows (via job)."""

    parameter_name = "job__project__in"
    related_filter_parameter = "job__project__campaign__id__exact"
    project_ref = "job__project_id"


class ImportJobAssetProjectListFilter(CampaignProjectListFilter):
    """Project filter for ImportItemAsset rows (via job)."""

    parameter_name = "import_item__job__project__in"
    related_filter_parameter = "import_item__job__project__campaign__id__exact"
    project_ref = "import_item__job__project_id"


class ImportCampaignListFilter(CampaignListFilter):
    """Campaign filter that excludes retired campaigns."""

    def lookups(
        self,
        request: HttpRequest,
        model_admin: admin.ModelAdmin,
    ) -> list[tuple[int | str, str]]:
        """
        Provide (id, title) choices for non-retired campaigns.

        Args:
            request (HttpRequest): Current admin request.
            model_admin (admin.ModelAdmin): Admin class in use.

        Returns:
            list[tuple[int | str, str]]: Campaign id/title pairs.
        """
        queryset = Campaign.objects.exclude(status=Campaign.Status.RETIRED)
        return list(queryset.values_list("id", "title").order_by("title"))


class ImportJobCampaignListFilter(ImportCampaignListFilter):
    """Campaign filter for ImportJob rows."""

    parameter_name = "project__campaign"
    status_filter_parameter = "project__campaign__status"


class ImportItemCampaignListFilter(ImportCampaignListFilter):
    """Campaign filter for ImportItem rows (via job)."""

    parameter_name = "job__project__campaign"
    status_filter_parameter = "job__project__campaign__status"


class ImportItemAssetCampaignListFilter(ImportCampaignListFilter):
    """Campaign filter for ImportItemAsset rows (via job)."""

    parameter_name = "import_item__job__project__campaign"
    status_filter_parameter = "import_item__job__project__campaign__status"


class BatchFilter(admin.SimpleListFilter):
    """Compact batch filter showing recent/incomplete and last complete batches."""

    title = _("Batch")
    parameter_name = "batch"

    def lookups(
        self,
        request: HttpRequest,
        model_admin: admin.ModelAdmin,
    ) -> list[tuple[str, str]]:
        """
        Show up to five batches with incomplete jobs, plus the currently filtered
        batch, and the most recent fully complete batch. Fill with more completed
        batches if there are fewer than five batches shown.

        Args:
            request (HttpRequest): Current admin request.
            model_admin (admin.ModelAdmin): Admin class in use.

        Returns:
            list[tuple[str, str]]: (value, label) pairs for batch selection.
        """
        queryset = model_admin.get_queryset(request)

        # Get up to 5 batches with incomplete jobs
        incomplete_batches = (
            queryset.filter(completed__isnull=True)
            .exclude(batch__isnull=True)
            .values("batch")
            .annotate(latest_created=Max("created"))
            .order_by("-latest_created")[:5]
        )

        batch_choices = {str(batch["batch"]) for batch in incomplete_batches}

        # Ensure the currently filtered batch is included
        current_batch = self.value()
        if current_batch:
            batch_choices.add(current_batch)

        # Fetch the most recent fully completed batch
        most_recent_complete_batch = (
            queryset.filter(batch__isnull=False)
            .values("batch")
            .annotate(
                latest_created=Max("created"),
                total_jobs=Count("id"),
                completed_jobs=Count("id", filter=Q(completed__isnull=False)),
            )
            .filter(total_jobs=F("completed_jobs"))  # Only fully completed batches
            .order_by("-latest_created")
            .first()
        )

        if most_recent_complete_batch:
            batch_choices.add(str(most_recent_complete_batch["batch"]))

        # If we still have fewer than 5, add more completed batches
        if len(batch_choices) < 5:
            additional_complete_batches = (
                queryset.filter(~Q(batch__in=batch_choices), batch__isnull=False)
                .values("batch")
                .annotate(
                    latest_created=Max("created"),
                    total_jobs=Count("id"),
                    completed_jobs=Count("id", filter=Q(completed__isnull=False)),
                )
                .filter(total_jobs=F("completed_jobs"))  # Only fully completed batches
                .order_by("-latest_created")
            )

            for batch in additional_complete_batches:
                if len(batch_choices) >= 5:
                    break
                batch_choices.add(str(batch["batch"]))

        return [(batch, batch[:12] + "...") for batch in batch_choices]

    def queryset(
        self,
        request: HttpRequest,
        queryset: QuerySet,
    ) -> QuerySet:
        """
        Filter the queryset to a specific batch when a value is selected.

        Args:
            request (HttpRequest): Current admin request.
            queryset (QuerySet): Base queryset for the changelist.

        Returns:
            QuerySet: Filtered queryset limited to the chosen batch.
        """
        batch_value = self.value()
        if batch_value:
            return queryset.filter(batch=batch_value)
        return queryset


class TaskStatusModelAdmin(admin.ModelAdmin):
    """
    Base ModelAdmin for task-like models with standard readonly fields.

    Also adds human-friendly timestamp display properties (e.g., "3 minutes
    ago") for common lifecycle fields.
    """

    readonly_fields = (
        "created",
        "modified",
        "last_started",
        "completed",
        "failed",
        "status",
        "task_id",
        "failure_reason",
        "retry_count",
        "failure_history",
        "status_history",
    )

    @staticmethod
    def generate_natural_timestamp_display_property(field_name: str):
        """
        Build a `naturaltime` display function for a timestamp field.

        The returned function is suitable for inclusion in `list_display`.
        It sets `short_description` and `admin_order_field` to match the
        provided field.

        Args:
            field_name (str): Name of the timestamp field on the model.

        Returns:
            callable: A function that takes an object and returns a
            human-readable string (or `None` when unset).
        """

        def inner(obj):
            try:
                value = getattr(obj, field_name)
            except AttributeError:
                return None
            if value:
                return naturaltime(value)
            else:
                return value

        inner.short_description = field_name.replace("_", " ").title()
        inner.admin_order_field = field_name
        return inner

    def __init__(self, *args, **kwargs):
        """
        Initialize and attach dynamic display_* timestamp helpers.

        For each known timestamp field, a `display_<field>` method is created
        that renders a human-friendly relative time and can be used in
        `list_display`.
        """
        for field_name in (
            "created",
            "modified",
            "last_started",
            "completed",
            "failed",
        ):
            setattr(
                self,
                f"display_{field_name}",
                self.generate_natural_timestamp_display_property(field_name),
            )

        super().__init__(*args, **kwargs)


@admin.register(ImportJob)
class ImportJobAdmin(TaskStatusModelAdmin):
    """Admin configuration for `ImportJob`."""

    readonly_fields = TaskStatusModelAdmin.readonly_fields + (
        "project",
        "created_by",
        "url",
    )
    list_display = (
        "display_created",
        "display_modified",
        "display_last_started",
        "display_completed",
        "url",
        "status",
    )
    list_filter = (
        LastStartedFilter,
        CompletedFilter,
        FailedFilter,
        ("created_by", admin.RelatedOnlyFieldListFilter),
        ImportJobCampaignListFilter,
        ImportJobProjectListFilter,
    )
    search_fields = ("url", "status")


@admin.register(ImportItem)
class ImportItemAdmin(TaskStatusModelAdmin):
    """Admin configuration for `ImportItem`."""

    readonly_fields = TaskStatusModelAdmin.readonly_fields + ("job", "item")

    list_display = (
        "display_created",
        "display_modified",
        "display_last_started",
        "display_completed",
        "url",
        "status",
    )
    list_filter = (
        LastStartedFilter,
        CompletedFilter,
        FailedFilter,
        ("job__created_by", admin.RelatedOnlyFieldListFilter),
        ImportItemCampaignListFilter,
        ImportJobItemProjectListFilter,
    )
    search_fields = ("url", "status")


@admin.register(ImportItemAsset)
class ImportItemAssetAdmin(TaskStatusModelAdmin):
    """Admin configuration for `ImportItemAsset`."""

    readonly_fields = TaskStatusModelAdmin.readonly_fields + (
        "import_item",
        "asset",
        "sequence_number",
    )

    list_display = (
        "display_created",
        "display_last_started",
        "display_completed",
        "url",
        "failure_reason",
        "status",
    )
    list_filter = (
        LastStartedFilter,
        CompletedFilter,
        FailedFilter,
        "failure_reason",
        ("import_item__job__created_by", admin.RelatedOnlyFieldListFilter),
        ImportItemAssetCampaignListFilter,
        ImportJobAssetProjectListFilter,
    )
    search_fields = ("url", "status")
    actions = (retry_download_task,)


@admin.register(VerifyAssetImageJob)
class VerifyAssetImageJobAdmin(TaskStatusModelAdmin):
    """Admin configuration for `VerifyAssetImageJob`."""

    readonly_fields = TaskStatusModelAdmin.readonly_fields + ("asset", "batch")
    list_display = (
        "display_created",
        "display_last_started",
        "asset",
        "batch",
        "failure_reason",
        "status",
    )
    list_filter = (
        LastStartedFilter,
        CompletedFilter,
        FailedFilter,
        "failure_reason",
        BatchFilter,
    )
    search_fields = ("status",)


@admin.register(DownloadAssetImageJob)
class DownloadAssetImageJobAdmin(TaskStatusModelAdmin):
    """Admin configuration for `DownloadAssetImageJob`."""

    readonly_fields = TaskStatusModelAdmin.readonly_fields + ("asset", "batch")
    list_display = (
        "display_created",
        "display_last_started",
        "asset",
        "batch",
        "failure_reason",
        "status",
    )
    list_filter = (
        LastStartedFilter,
        CompletedFilter,
        FailedFilter,
        "failure_reason",
        BatchFilter,
    )
    search_fields = ("status",)
