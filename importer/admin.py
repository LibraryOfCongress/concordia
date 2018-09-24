from django.contrib import admin, messages

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


class NullableTimestampFilter(admin.SimpleListFilter):
    """
    Base class for Admin list filters which define whether a datetime field has
    a value or is null
    """

    # Title displayed on the list filter URL
    title = ""
    # Model field name:
    parameter_name = ""
    # Choices displayed
    lookup_labels = ("NULL", "NOT NULL")

    def lookups(self, request, model_admin):
        return zip(("null", "not-null"), self.lookup_labels)

    def queryset(self, request, queryset):
        kwargs = {"%s__isnull" % self.parameter_name: True}
        if self.value() == "null":
            return queryset.filter(**kwargs)
        elif self.value() == "not-null":
            return queryset.exclude(**kwargs)
        return queryset


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


class ImportJobAdmin(admin.ModelAdmin):
    list_display = ("created", "modified", "last_started", "completed", "url", "status")
    list_filter = (
        "created_by",
        "project",
        LastStartedFilter,
        CompletedFilter,
        FailedFilter,
    )
    search_fields = ("url", "status")


class ImportItemAdmin(admin.ModelAdmin):
    list_display = ("created", "modified", "last_started", "completed", "url", "status")
    list_filter = (
        "job__created_by",
        "job__project",
        LastStartedFilter,
        CompletedFilter,
        FailedFilter,
    )
    search_fields = ("url", "status")


class ImportItemAssetAdmin(admin.ModelAdmin):
    list_display = ("created", "modified", "last_started", "completed", "url", "status")
    list_filter = (
        "import_item__job__created_by",
        "import_item__job__project",
        LastStartedFilter,
        CompletedFilter,
        FailedFilter,
    )
    search_fields = ("url", "status")
    actions = (retry_download_task,)


admin.site.register(ImportJob, ImportJobAdmin)
admin.site.register(ImportItem, ImportItemAdmin)
admin.site.register(ImportItemAsset, ImportItemAssetAdmin)
