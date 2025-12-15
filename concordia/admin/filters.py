from django.contrib import admin
from django.db.models import Exists, OuterRef
from django.utils.translation import gettext_lazy as _

from ..models import Campaign, Project, Topic, Transcription


class NullableTimestampFilter(admin.SimpleListFilter):
    """
    Base class for admin list filters that test if a datetime field is set.

    Provides "null" and "not-null" choices based on a configured
    `parameter_name` that points to a `DateTimeField` or similar attribute.
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
    """
    Filter transcriptions by whether the `submitted` timestamp is set.
    """

    title = "Submitted"
    parameter_name = "submitted"
    lookup_labels = ("Pending", "Submitted")


class AcceptedFilter(NullableTimestampFilter):
    """
    Filter transcriptions by whether the `accepted` timestamp is set.
    """

    title = "Accepted"
    parameter_name = "accepted"
    lookup_labels = ("Pending", "Accepted")


class RejectedFilter(NullableTimestampFilter):
    """
    Filter transcriptions by whether the `rejected` timestamp is set.
    """

    title = "Rejected"
    parameter_name = "rejected"
    lookup_labels = ("Pending", "Rejected")


class CampaignListFilter(admin.SimpleListFilter):
    """
    Base class for campaign filters used in admin changelists.

    Filters by a campaign identifier stored in `parameter_name` and
    optionally narrows results by campaign status when a related status
    query parameter is present.
    """

    title = "Campaign"
    template = "admin/long_name_filter.html"

    def lookups(self, request, model_admin):
        queryset = Campaign.objects.exclude(status=Campaign.Status.RETIRED)
        if self.status_filter_parameter in request.GET:
            queryset = queryset.filter(status=request.GET[self.status_filter_parameter])
        return queryset.values_list("id", "title").order_by("title")

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(**{self.parameter_name: self.value()})
        return queryset


class CardCampaignListFilter(admin.SimpleListFilter):
    """
    Filter cards by the campaign that owns their card family.

    Shows only campaigns with a non-null `card_family` and restricts
    cards to those within the selected campaign's family.
    """

    title = _("campaign")
    parameter_name = "campaign"

    def lookups(self, request, model_admin):
        return Campaign.objects.exclude(card_family__isnull=True).values_list(
            "pk", "title"
        )

    def queryset(self, request, queryset):
        campaign_id = self.value()
        if campaign_id:
            card_family = Campaign.objects.get(pk=campaign_id).card_family
            if card_family is None:
                pks = []
            else:
                pks = card_family.cards.values_list("pk", flat=True)
            queryset = queryset.filter(id__in=pks)
        return queryset


class TopicListFilter(admin.SimpleListFilter):
    """
    Base class for topic filters used in admin changelists.

    Filters by topic identifier using the configured `parameter_name`.
    """

    title = "Topic"
    template = "admin/long_name_filter.html"
    parameter_name = "topic__id__exact"

    def lookups(self, request, model_admin):
        queryset = Topic.objects.all()
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
    """
    Base filter for site report campaigns that supports empty-campaign rows.

    Extends `CampaignListFilter` to optionally include an explicit "no
    campaign" choice controlled by `include_empty_choice` and the
    `lookup_kwarg_isnull` query parameter.
    """

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


class HelpfulLinkCampaignListFilter(CampaignListFilter):
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


class UserAssetTagCollectionCampaignListFilter(CampaignListFilter):
    parameter_name = "asset__item__project__campaign__id__exact"
    status_filter_parameter = "asset__item__project__campaign__status"


class NextAssetCampaignListFilter(CampaignListFilter):
    parameter_name = "campaign__id__exact"

    def lookups(self, request, model_admin):
        campaigns = Campaign.objects.filter(
            pk__in=model_admin.model.objects.values_list(
                "campaign_id", flat=True
            ).distinct()
        )
        return campaigns.values_list("id", "title").order_by("title")


class CampaignProjectListFilter(admin.SimpleListFilter):
    """
    Base class for project filters grouped by campaign.

    Provides a project dropdown whose choices can be narrowed by a related
    campaign filter, then filters the changelist using `project_ref`.
    """

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


class ItemProjectListFilter(CampaignProjectListFilter):
    parameter_name = "project__in"
    related_filter_parameter = "project__campaign__id__exact"
    project_ref = "project_id"


class AssetProjectListFilter(CampaignProjectListFilter):
    parameter_name = "item__project__in"
    related_filter_parameter = "item__project__campaign__id__exact"
    project_ref = "item__project_id"


class TranscriptionProjectListFilter(CampaignProjectListFilter):
    parameter_name = "asset__item__project__in"
    related_filter_parameter = "asset__item__project__campaign__id__exact"
    project_ref = "asset__item__project_id"


class CampaignStatusListFilter(admin.SimpleListFilter):
    """
    Base class for campaign status filters.

    Filters changelist rows by campaign status using the configured
    `parameter_name` and the `Campaign.Status` choices.
    """

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


class HelpfulLinkCampaignStatusListFilter(CampaignStatusListFilter):
    parameter_name = "campaign__status"


class TranscriptionCampaignStatusListFilter(CampaignStatusListFilter):
    parameter_name = "asset__item__project__campaign__status"


class TagCampaignStatusListFilter(CampaignStatusListFilter):
    parameter_name = "userassettagcollection__asset__item__project__campaign__status"


class UserAssetTagCollectionCampaignStatusListFilter(CampaignStatusListFilter):
    parameter_name = "asset__item__project__campaign__status"


class UserProfileActivityCampaignStatusListFilter(CampaignStatusListFilter):
    parameter_name = "campaign__status"


class BooleanFilter(admin.SimpleListFilter):
    """
    Base class for simple yes/no boolean filters.

    Provides "Yes" and "No" choices and filters using the configured
    `parameter_name`.
    """

    def lookups(self, request, model_admin):
        return [
            (True, _("Yes")),
            (False, _("No")),
        ]

    def queryset(self, request, queryset):
        if self.value() is None:
            return queryset
        else:
            return queryset.filter(**{self.parameter_name: self.value()})


class OcrGeneratedFilter(BooleanFilter):
    title = "OCR Generated"
    parameter_name = "ocr_generated"


class OcrOriginatedFilter(BooleanFilter):
    title = "OCR Originated"
    parameter_name = "ocr_originated"


class SupersededListFilter(admin.SimpleListFilter):
    """
    Filter transcriptions by whether they have been superseded.

    Uses an `Exists` subquery on the `Transcription.supersedes` relation to
    efficiently determine superseded rows.
    """

    title = "superseded"
    parameter_name = "superseded"

    def lookups(self, request, model_admin):
        return (("yes", "Superseded"), ("no", "Not superseded"))

    def queryset(self, request, queryset):
        # Uses Exists to make joining cheaper
        superseded_exists = Transcription.objects.filter(supersedes=OuterRef("pk"))
        val = self.value()
        if val == "yes":
            return queryset.annotate(_is_superseded=Exists(superseded_exists)).filter(
                _is_superseded=True
            )
        if val == "no":
            return queryset.annotate(_is_superseded=Exists(superseded_exists)).filter(
                _is_superseded=False
            )
        return queryset
