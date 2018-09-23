from django.contrib import admin

from .models import ImportItem, ImportItemAsset, ImportJob


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
    title = u"Last Started"
    parameter_name = u"last_started"
    lookup_labels = ("Unstarted", "Started")


class CompletedFilter(NullableTimestampFilter):
    title = u"Completed"
    parameter_name = u"completed"
    lookup_labels = ("Incomplete", "Completed")


class FailedFilter(NullableTimestampFilter):
    title = u"Failed"
    parameter_name = u"failed"
    lookup_labels = ("Has not failed", "Has failed")


class ImportJobAdmin(admin.ModelAdmin):
    list_display = (
        "created",
        "modified",
        "last_started",
        "completed",
        "source_url",
        "status",
    )
    list_filter = (
        "created_by",
        "project",
        LastStartedFilter,
        CompletedFilter,
        FailedFilter,
    )
    search_fields = ("source_url", "status")


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


admin.site.register(ImportJob, ImportJobAdmin)
admin.site.register(ImportItem, ImportItemAdmin)
admin.site.register(ImportItemAsset, ImportItemAssetAdmin)
