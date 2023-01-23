from django.contrib import admin, messages
from django.contrib.humanize.templatetags.humanize import naturaltime

from concordia.admin.filters import CampaignProjectListFilter, NullableTimestampFilter

from .models import ImportItem, ImportItemAsset, ImportJob
from .tasks import download_asset_task


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


class TaskStatusModelAdmin(admin.ModelAdmin):
    readonly_fields = (
        "created",
        "modified",
        "last_started",
        "completed",
        "failed",
        "status",
        "task_id",
    )

    @staticmethod
    def generate_natural_timestamp_display_property(field_name):
        def inner(obj):
            value = getattr(obj, field_name)
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
        "project__campaign",
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
        "job__project__campaign",
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
        ("import_item__job__created_by", admin.RelatedOnlyFieldListFilter),
        "import_item__job__project__campaign",
        ImportJobAssetProjectListFilter,
    )
    search_fields = ("url", "status")
    actions = (retry_download_task,)
