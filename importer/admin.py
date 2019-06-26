from django.contrib import admin, messages
from django.contrib.humanize.templatetags.humanize import naturaltime

from concordia.admin.filters import NullableTimestampFilter

from .models import ImportItem, ImportItemAsset, ImportJob
from .tasks import download_asset_task


def retry_download_task(modeladmin, request, queryset):
    """
    Queue an asset download task for another attempt
    """

    pks = queryset.values_list("pk", flat=True)
    for pk in pks:
        download_asset_task.delay(pk)
    messages.add_message(request, messages.INFO, f"Queued %d tasks" % len(pks))


retry_download_task.short_description = "Retry import"


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
        "project",
        "created_by",
    )
    search_fields = ("url", "status")


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
        "job__project",
        "job__created_by",
    )
    search_fields = ("url", "status")


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
        "import_item__job__project",
        "import_item__job__created_by",
    )
    search_fields = ("url", "status")
    actions = (retry_download_task,)


admin.site.register(ImportJob, ImportJobAdmin)
admin.site.register(ImportItem, ImportItemAdmin)
admin.site.register(ImportItemAsset, ImportItemAssetAdmin)
