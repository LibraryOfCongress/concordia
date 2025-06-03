from django.contrib import admin, messages
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.db.models import Count, F, Max, Q
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
def retry_download_task(modeladmin, request, queryset):
    """
    Queue an asset download task for another attempt
    """

    pks = queryset.values_list("pk", flat=True)
    for pk in pks:
        download_asset_task.delay(pk)
    messages.add_message(request, messages.INFO, "Queued %d tasks" % len(pks))


class LastStartedFilter(NullableTimestampFilter):
    title = "Last Started"
    parameter_name = "last_started"
    lookup_labels = ("Unstarted", "Started")


class CompletedFilter(NullableTimestampFilter):
    title = "Completed"
    parameter_name = "completed"
    lookup_labels = ("Incomplete", "Completed")


class FailedFilter(NullableTimestampFilter):
    title = "Failed"
    parameter_name = "failed"
    lookup_labels = ("Has not failed", "Has failed")


class ImportJobProjectListFilter(CampaignProjectListFilter):
    parameter_name = "project__in"
    related_filter_parameter = "project__campaign__id__exact"
    project_ref = "project_id"


class ImportJobItemProjectListFilter(CampaignProjectListFilter):
    parameter_name = "job__project__in"
    related_filter_parameter = "job__project__campaign__id__exact"
    project_ref = "job__project_id"


class ImportJobAssetProjectListFilter(CampaignProjectListFilter):
    parameter_name = "import_item__job__project__in"
    related_filter_parameter = "import_item__job__project__campaign__id__exact"
    project_ref = "import_item__job__project_id"


class ImportCampaignListFilter(CampaignListFilter):
    def lookups(self, request, model_admin):
        queryset = Campaign.objects.exclude(status=Campaign.Status.RETIRED)
        return queryset.values_list("id", "title").order_by("title")


class ImportJobCampaignListFilter(ImportCampaignListFilter):
    parameter_name = "project__campaign"
    status_filter_parameter = "project__campaign__status"


class ImportItemCampaignListFilter(ImportCampaignListFilter):
    parameter_name = "job__project__campaign"
    status_filter_parameter = "job__project__campaign__status"


class ImportItemAssetCampaignListFilter(ImportCampaignListFilter):
    parameter_name = "import_item__job__project__campaign"
    status_filter_parameter = "import_item__job__project__campaign__status"


class BatchFilter(admin.SimpleListFilter):
    title = _("Batch")
    parameter_name = "batch"

    def lookups(self, request, model_admin):
        """
        Show up to five batches with incomplete jobs, plus the currently filtered batch,
        and the most recent fully complete batch. Fill with more completed batches if
        there are fewer than five batches shown.
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

    def queryset(self, request, queryset):
        batch_value = self.value()
        if batch_value:
            return queryset.filter(batch=batch_value)
        return queryset


class TaskStatusModelAdmin(admin.ModelAdmin):
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
    def generate_natural_timestamp_display_property(field_name):
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
