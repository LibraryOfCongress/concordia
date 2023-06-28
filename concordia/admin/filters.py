from django.contrib import admin

from ..models import Campaign, Project


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
        return zip(("null", "not-null"), self.lookup_labels, strict=False)

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


class CampaignListFilter(admin.SimpleListFilter):
    """
    Base class for admin campaign filters
    """

    title = "Campaign"
    template = "admin/long_name_filter.html"

    def lookups(self, request, model_admin):
        queryset = Campaign.objects.all()
        if self.status_filter_parameter in request.GET:
            queryset = queryset.filter(status=request.GET[self.status_filter_parameter])
        return queryset.values_list("id", "title").order_by("title")

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(**{self.parameter_name: self.value()})
        return queryset


class ProjectCampaignListFilter(CampaignListFilter):
    parameter_name = "campaign__id__exact"
    status_filter_parameter = "campaign__status"


class ItemCampaignListFilter(CampaignListFilter):
    parameter_name = "project__campaign__id__exact"
    status_filter_parameter = "project__campaign__status"


class AssetCampaignListFilter(CampaignListFilter):
    parameter_name = "item__project__campaign__id__exact"
    status_filter_parameter = "item__project__campaign__status"


class UserProfileActivityCampaignListFilter(CampaignListFilter):
    parameter_name = "campaign__id__exact"
    status_filter_parameter = "campaign__status"


class SiteReportCampaignListBaseFilter(CampaignListFilter):
    lookup_kwarg_isnull = "campaign__isnull"
    include_empty_choice = True

    def __init__(self, request, params, model, model_admin):
        self.empty_value_display = model_admin.get_empty_value_display()
        self.lookup_val_isnull = params.get(self.lookup_kwarg_isnull)
        super().__init__(request, params, model, model_admin)

    def has_output(self):
        if self.include_empty_choice:
            extra = 1
        else:
            extra = 0
        return len(self.lookup_choices) + extra > 1

    def expected_parameters(self):
        return [self.parameter_name, self.lookup_kwarg_isnull]

    def choices(self, changelist):
        yield {
            "selected": self.value() is None and not self.lookup_val_isnull,
            "query_string": changelist.get_query_string(
                remove=[self.parameter_name, self.lookup_kwarg_isnull]
            ),
            "display": "All",
        }
        for lookup, title in self.lookup_choices:
            yield {
                "selected": self.value() == str(lookup),
                "query_string": changelist.get_query_string(
                    {self.parameter_name: lookup}, self.lookup_kwarg_isnull
                ),
                "display": title,
            }
        if self.include_empty_choice:
            yield {
                "selected": bool(self.lookup_val_isnull),
                "query_string": changelist.get_query_string(
                    {self.lookup_kwarg_isnull: "True"}, [self.parameter_name]
                ),
                "display": self.empty_value_display,
            }


class SiteReportSortedCampaignListFilter(SiteReportCampaignListBaseFilter):
    title = "Sorted Campaign"
    parameter_name = "campaign__id__exact"
    status_filter_parameter = "campaign__status"


class SiteReportCampaignListFilter(SiteReportCampaignListBaseFilter):
    parameter_name = "campaign__id__exact"
    status_filter_parameter = "campaign__status"

    def lookups(self, request, model_admin):
        return Campaign.objects.values_list("id", "title")


class ResourceCampaignListFilter(CampaignListFilter):
    title = "Campaign Sorted"
    parameter_name = "campaign__id__exact"
    status_filter_parameter = "campaign__status"


class TagCampaignListFilter(CampaignListFilter):
    parameter_name = "userassettagcollection__asset__item__project__campaign__id__exact"
    status_filter_parameter = (
        "userassettagcollection__asset__item__project__campaign__status"
    )


class TranscriptionCampaignListFilter(CampaignListFilter):
    parameter_name = "asset__item__project__campaign__id__exact"
    status_filter_parameter = "asset__item__project__campaign__status"


class CampaignProjectListFilter(admin.SimpleListFilter):
    title = "ProjectRedux"
    parameter_name = "project"
    related_filter_parameter = ""
    project_ref = ""
    template = "admin/long_name_filter.html"

    def lookups(self, request, model_admin):
        list_of_questions = []
        queryset = Project.objects.order_by("campaign_id")
        if self.related_filter_parameter in request.GET:
            queryset = queryset.filter(
                campaign_id=request.GET[self.related_filter_parameter]
            )
        for project in queryset:
            list_of_questions.append((str(project.id), project.title))
        return sorted(list_of_questions, key=lambda tp: tp[1])

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(**{self.project_ref: self.value()})
        return queryset


class ItemProjectListFilter2(CampaignProjectListFilter):
    parameter_name = "project__in"
    related_filter_parameter = "project__campaign__id__exact"
    project_ref = "project_id"


class AssetProjectListFilter2(CampaignProjectListFilter):
    parameter_name = "item__project__in"
    related_filter_parameter = "item__project__campaign__id__exact"
    project_ref = "item__project_id"


class TranscriptionProjectListFilter(CampaignProjectListFilter):
    parameter_name = "asset__item__project__in"
    related_filter_parameter = "asset__item__project__campaign__id__exact"
    project_ref = "asset__item__project_id"


class CampaignStatusListFilter(admin.SimpleListFilter):
    """Base class for campaign status list filters"""

    title = "Campaign status"

    def lookups(self, request, model_admin):
        return Campaign.Status.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(**{self.parameter_name: self.value()})
        return queryset


class AssetCampaignStatusListFilter(CampaignStatusListFilter):
    parameter_name = "item__project__campaign__status"


class ItemCampaignStatusListFilter(CampaignStatusListFilter):
    parameter_name = "project__campaign__status"


class ProjectCampaignStatusListFilter(CampaignStatusListFilter):
    parameter_name = "campaign__status"


class ResourceCampaignStatusListFilter(CampaignStatusListFilter):
    parameter_name = "campaign__status"


class TranscriptionCampaignStatusListFilter(CampaignStatusListFilter):
    parameter_name = "asset__item__project__campaign__status"


class TagCampaignStatusListFilter(CampaignStatusListFilter):
    parameter_name = "userassettagcollection__asset__item__project__campaign__status"


class UserAssetTagCollectionCampaignStatusListFilter(CampaignStatusListFilter):
    parameter_name = "asset__item__project__campaign__status"


class UserProfileActivityCampaignStatusListFilter(CampaignStatusListFilter):
    parameter_name = "campaign__status"
