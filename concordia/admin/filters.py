from django.contrib import admin


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


class SubmittedFilter(NullableTimestampFilter):
    title = "Submitted"
    parameter_name = "submitted"
    lookup_labels = ("Pending", "Submitted")


class AcceptedFilter(NullableTimestampFilter):
    title = "Accepted"
    parameter_name = "accepted"
    lookup_labels = ("Pending", "Accepted")


class RejectedFilter(NullableTimestampFilter):
    title = "Rejected"
    parameter_name = "rejected"
    lookup_labels = ("Pending", "Rejected")
