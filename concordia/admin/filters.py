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


class ProjectCampaignListFilter(admin.SimpleListFilter):
    """
    Base class for admin campaign filters
    """

    # Title displayed on the list filter URL
    title = "Campaign"
    # Model field name:
    parameter_name = "campaign__id__exact"
    template = "admin/long_name_filter.html"

    def lookups(self, request, model_admin):
        list_of_questions = []
        queryset = Campaign.objects.order_by("title")
        for campaign in queryset:
            list_of_questions.append((str(campaign.id), campaign.title))
        return list_of_questions

    def queryset(self, request, queryset):
        fkey_field = self.parameter_name
        if self.value():
            return queryset.filter(**{fkey_field: self.value()})
        return queryset


class ItemCampaignListFilter(admin.SimpleListFilter):
    """
    Base class for admin campaign filters
    """

    # Title displayed on the list filter URL
    title = "Campaign"
    # Model field name:
    parameter_name = "project__campaign__id__exact"
    template = "admin/long_name_filter.html"

    def lookups(self, request, model_admin):
        list_of_questions = []
        queryset = Campaign.objects.order_by("title")
        for campaign in queryset:
            list_of_questions.append((str(campaign.id), campaign.title))
        return list_of_questions

    def queryset(self, request, queryset):
        fkey_field = self.parameter_name
        if self.value():
            return queryset.filter(**{fkey_field: self.value()})
        return queryset


class AssetCampaignListFilter(admin.SimpleListFilter):
    """
    Base class for admin campaign filters
    """

    # Title displayed on the list filter URL
    title = "Campaign"
    # Model field name:
    parameter_name = "item__project__campaign__id__exact"
    template = "admin/long_name_filter.html"

    def lookups(self, request, model_admin):
        list_of_questions = []
        queryset = Campaign.objects.order_by("title")
        for campaign in queryset:
            list_of_questions.append((str(campaign.id), campaign.title))
        return list_of_questions

    def queryset(self, request, queryset):
        fkey_field = self.parameter_name
        if self.value():
            return queryset.filter(**{fkey_field: self.value()})
        return queryset


class SiteReportSortedCampaignListFilter(admin.SimpleListFilter):
    """
    Base class for admin campaign filters
    """

    # Title displayed on the list filter URL
    title = "Sorted Campaign"
    # Model field name:
    parameter_name = "campaign__id__exact"
    template = "admin/long_name_filter.html"

    def lookups(self, request, model_admin):
        list_of_questions = []
        queryset = Campaign.objects.order_by("title")
        for campaign in queryset:
            list_of_questions.append((str(campaign.id), campaign.title))
        return list_of_questions

    def queryset(self, request, queryset):
        fkey_field = self.parameter_name
        if self.value():
            return queryset.filter(**{fkey_field: self.value()})
        return queryset


class SiteReportCampaignListFilter(admin.SimpleListFilter):
    title = "Campaign"
    parameter_name = "campaign__id__exact"
    template = "admin/long_name_filter.html"

    def lookups(self, request, model_admin):
        list_of_questions = []
        queryset = Campaign.objects.all()
        for campaign in queryset:
            list_of_questions.append((str(campaign.id), campaign.title))
        return list_of_questions

    def queryset(self, request, queryset):
        fkey_field = self.parameter_name
        if self.value():
            return queryset.filter(**{fkey_field: self.value()})
        return queryset


class ResourceCampaignListFilter(admin.SimpleListFilter):
    """
    Base class for admin campaign filters
    """

    # Title displayed on the list filter URL
    title = "Campaign Sorted"
    # Model field name:
    parameter_name = "campaign__id__exact"
    template = "admin/long_name_filter.html"

    def lookups(self, request, model_admin):
        list_of_questions = []
        queryset = Campaign.objects.order_by("title")
        for campaign in queryset:
            list_of_questions.append((str(campaign.id), campaign.title))
        return list_of_questions

    def queryset(self, request, queryset):
        fkey_field = self.parameter_name
        if self.value():
            return queryset.filter(**{fkey_field: self.value()})
        return queryset


class TagCampaignListFilter(admin.SimpleListFilter):
    title = "Campaign"
    parameter_name = "userassettagcollection__asset__item__project__campaign__id__exact"
    template = "admin/long_name_filter.html"

    def lookups(self, request, model_admin):
        list_of_questions = []
        queryset = Campaign.objects.order_by("title")
        for campaign in queryset:
            list_of_questions.append((str(campaign.id), campaign.title))
        return list_of_questions

    def queryset(self, request, queryset):
        fkey_field = self.parameter_name
        if self.value():
            return queryset.filter(**{fkey_field: self.value()})
        return queryset


class TranscriptionCampaignListFilter(admin.SimpleListFilter):
    """
    Base class for admin campaign filters
    """

    # Title displayed on the list filter URL
    title = "Campaign"
    # Model field name:
    parameter_name = "asset__item__project__campaign__id__exact"
    template = "admin/long_name_filter.html"

    def lookups(self, request, model_admin):
        list_of_questions = []
        queryset = Campaign.objects.order_by("title")
        for campaign in queryset:
            list_of_questions.append((str(campaign.id), campaign.title))
        return list_of_questions

    def queryset(self, request, queryset):
        fkey_field = self.parameter_name
        if self.value():
            return queryset.filter(**{fkey_field: self.value()})
        return queryset


class CampaignProjectListFilter(admin.SimpleListFilter):
    """
    Base class for admin campaign project filters
    """

    # Title displayed on the list filter URL
    title = "ProjectRedux"
    # Model field name:
    parameter_name = "project"
    # Custom attributes
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
        fkey_field = self.project_ref
        if self.value():
            return queryset.filter(**{fkey_field: self.value()})
        return queryset


class ItemProjectListFilter2(CampaignProjectListFilter):
    parameter_name = "project__in"
    related_filter_parameter = "project__campaign__id__exact"
    project_ref = "project_id"
    template = "admin/long_name_filter.html"


class AssetProjectListFilter2(CampaignProjectListFilter):
    parameter_name = "item__project__in"
    related_filter_parameter = "item__project__campaign__id__exact"
    project_ref = "item__project_id"
    template = "admin/long_name_filter.html"


class TranscriptionProjectListFilter(CampaignProjectListFilter):
    parameter_name = "asset__item__project__in"
    related_filter_parameter = "asset__item__project__campaign__id__exact"
    project_ref = "asset__item__project_id"
    template = "admin/long_name_filter.html"


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
