from django.contrib import admin

from ..models import Project, Campaign


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
    # Custom attributes
    project_ref = "campaign__id__exact"

    def lookups(self, request, model_admin):

        list_of_questions = []
        queryset = Campaign.objects.order_by("id")
        for campaign in queryset:
            list_of_questions.append((str(campaign.id), campaign.title))
        return sorted(list_of_questions, key=lambda tp: tp[1])

    def queryset(self, request, queryset):
        fkey_field = self.project_ref
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
    # Custom attributes
    project_ref = "project__campaign__id__exact"

    def lookups(self, request, model_admin):

        list_of_questions = []
        queryset = Campaign.objects.order_by("id")
        for campaign in queryset:
            list_of_questions.append((str(campaign.id), campaign.title))
        return sorted(list_of_questions, key=lambda tp: tp[1])

    def queryset(self, request, queryset):
        fkey_field = self.project_ref
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
    # Custom attributes
    project_ref = "item__project__campaign__id__exact"

    def lookups(self, request, model_admin):

        list_of_questions = []
        queryset = Campaign.objects.order_by("id")
        for campaign in queryset:
            list_of_questions.append((str(campaign.id), campaign.title))
        return sorted(list_of_questions, key=lambda tp: tp[1])

    def queryset(self, request, queryset):
        fkey_field = self.project_ref
        if self.value():
            return queryset.filter(**{fkey_field: self.value()})
        return queryset


class SiteCampaignListFilter(admin.SimpleListFilter):
    """
    Base class for admin campaign filters
    """

    # Title displayed on the list filter URL
    title = "Campaign"
    # Model field name:
    parameter_name = "campaign__id__exact"
    # Custom attributes
    project_ref = "campaign__id__exact"
    # Null attribute
    null_ref = "campaign_isnull"

    def lookups(self, request, model_admin):

        list_of_questions = []
        queryset = Campaign.objects.order_by("id")
        for campaign in queryset:
            list_of_questions.append((str(campaign.id), campaign.title))
        list_of_questions.append((str("0"), "-"))
        return sorted(list_of_questions, key=lambda tp: tp[1])

    def queryset(self, request, queryset):
        fkey_field = self.project_ref
        fnull_field = self.null_ref
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
    # Custom attributes
    project_ref = "asset__item__project__campaign__id__exact"

    def lookups(self, request, model_admin):

        list_of_questions = []
        queryset = Campaign.objects.order_by("id")
        for campaign in queryset:
            list_of_questions.append((str(campaign.id), campaign.title))
        return sorted(list_of_questions, key=lambda tp: tp[1])

    def queryset(self, request, queryset):
        fkey_field = self.project_ref
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


class AssetProjectListFilter2(CampaignProjectListFilter):
    parameter_name = "item__project__in"
    related_filter_parameter = "item__project__campaign__id__exact"
    project_ref = "item__project_id"


class TranscriptionProjectListFilter(CampaignProjectListFilter):
    parameter_name = "asset__item__project__in"
    related_filter_parameter = "asset__item__project__campaign__id__exact"
    project_ref = "asset__item__project_id"
