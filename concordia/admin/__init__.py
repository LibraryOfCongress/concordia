import logging
from urllib.parse import urljoin

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.admin.options import get_content_type_for_model
from django.contrib.auth import get_permission_codename
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.models import User
from django.db.models import Count
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.template.defaultfilters import truncatechars
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.views.decorators.csrf import csrf_protect
from django_admin_multiple_choice_list_filter.list_filters import (
    MultipleChoiceListFilter,
)
from tabular_export.admin import export_to_csv_action, export_to_excel_action
from tabular_export.core import export_to_csv_response, flatten_queryset

from exporter import views as exporter_views
from importer.tasks import import_items_into_project_from_url

from ..models import (
    Asset,
    AssetTranscriptionReservation,
    Banner,
    Campaign,
    CampaignRetirementProgress,
    CarouselSlide,
    Item,
    Project,
    Resource,
    ResourceFile,
    SimpleContentBlock,
    SimplePage,
    SiteReport,
    Tag,
    Topic,
    Transcription,
    UserAssetTagCollection,
    UserProfileActivity,
    UserRetiredCampaign,
)
from ..tasks import retire_campaign
from ..views import ReportCampaignView
from .actions import (
    anonymize_action,
    change_status_to_completed,
    change_status_to_in_progress,
    change_status_to_needs_review,
    publish_action,
    publish_item_action,
    unpublish_action,
    unpublish_item_action,
)
from .filters import (
    AcceptedFilter,
    AssetCampaignListFilter,
    AssetCampaignStatusListFilter,
    AssetProjectListFilter2,
    ItemCampaignListFilter,
    ItemCampaignStatusListFilter,
    ItemProjectListFilter2,
    ProjectCampaignListFilter,
    ProjectCampaignStatusListFilter,
    RejectedFilter,
    ResourceCampaignListFilter,
    ResourceCampaignStatusListFilter,
    SiteReportCampaignListFilter,
    SiteReportSortedCampaignListFilter,
    SubmittedFilter,
    TagCampaignListFilter,
    TagCampaignStatusListFilter,
    TranscriptionCampaignListFilter,
    TranscriptionCampaignStatusListFilter,
    TranscriptionProjectListFilter,
    UserAssetTagCollectionCampaignStatusListFilter,
    UserProfileActivityCampaignListFilter,
    UserProfileActivityCampaignStatusListFilter,
)
from .forms import (
    AdminItemImportForm,
    BleachedDescriptionAdminForm,
    SimpleContentBlockAdminForm,
)


class ProjectListFilter(MultipleChoiceListFilter):
    title = "Project"

    def lookups(self, request, model_admin):
        choices = Project.objects.values_list("pk", "title")
        return tuple(choices)


logger = logging.getLogger(__name__)


class AssetProjectListFilter(ProjectListFilter):
    parameter_name = "item__project__in"


class ItemProjectListFilter(ProjectListFilter):
    parameter_name = "project__in"


class ConcordiaUserAdmin(UserAdmin):
    list_display = UserAdmin.list_display + ("date_joined", "transcription_count")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.annotate(Count("transcription"))
        return qs

    @admin.display(ordering="transcription__count")
    def transcription_count(self, obj):
        return obj.transcription__count

    EXPORT_FIELDS = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_active",
        "is_staff",
        "is_superuser",
        "date_joined",
        "last_login",
        "transcription__count",
    )

    def export_users_as_csv(self, request, queryset):
        return export_to_csv_action(
            self, request, queryset, field_names=self.EXPORT_FIELDS
        )

    def export_users_as_excel(self, request, queryset):
        return export_to_excel_action(
            self, request, queryset, field_names=self.EXPORT_FIELDS
        )

    actions = (anonymize_action, export_users_as_csv, export_users_as_excel)


admin.site.unregister(User)
admin.site.register(User, ConcordiaUserAdmin)


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = (
        "text",
        "active",
    )


class CustomListDisplayFieldsMixin:
    """
    Mixin which provides some custom text formatters for list display fields
    used on multiple models
    """

    @admin.display(description="Description")
    def truncated_description(self, obj):
        return truncatechars(obj.description, 200)

    @admin.display(description="Metadata")
    def truncated_metadata(self, obj):
        if obj.metadata:
            return format_html("<code>{}</code>", truncatechars(obj.metadata, 200))
        else:
            return ""


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin, CustomListDisplayFieldsMixin):
    form = BleachedDescriptionAdminForm

    list_display = (
        "title",
        "status",
        "published",
        "unlisted",
        "display_on_homepage",
        "ordering",
        "launch_date",
        "completed_date",
    )
    list_editable = (
        "display_on_homepage",
        "ordering",
        "published",
        "unlisted",
        "status",
        "launch_date",
        "completed_date",
    )
    list_display_links = ("title",)
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ["title", "description"]
    list_filter = ("published", "display_on_homepage", "unlisted", "status")

    actions = (publish_action, unpublish_action)

    def get_urls(self):
        urls = super().get_urls()

        app_label = self.model._meta.app_label
        model_name = self.model._meta.model_name

        custom_urls = [
            path(
                "exportCSV/<path:campaign_slug>",
                exporter_views.ExportCampaignToCSV.as_view(),
                name=f"{app_label}_{model_name}_export-csv",
            ),
            path(
                "exportBagIt/<path:campaign_slug>",
                exporter_views.ExportCampaignToBagIt.as_view(),
                name=f"{app_label}_{model_name}_export-bagit",
            ),
            path(
                "report/<path:campaign_slug>",
                ReportCampaignView.as_view(),
                name=f"{app_label}_{model_name}_report",
            ),
            path(
                "retire/<path:campaign_slug>",
                self.admin_site.admin_view(self.retire),
                name=f"{app_label}_{model_name}_retire",
            ),
        ]

        return custom_urls + urls

    @method_decorator(csrf_protect)
    @method_decorator(permission_required("concordia.retire_campaign"))
    @method_decorator(permission_required("concordia.delete_project"))
    @method_decorator(permission_required("concordia.delete_item"))
    @method_decorator(permission_required("concordia.delete_asset"))
    @method_decorator(permission_required("concordia.delete_transcription"))
    @method_decorator(permission_required("concordia.delete_import_item_asset"))
    def retire(self, request, campaign_slug):
        try:
            campaign = Campaign.objects.filter(slug=campaign_slug)[0]
        except IndexError:
            return self._get_obj_does_not_exist_redirect(
                request, self.opts, campaign_slug
            )

        projects = campaign.project_set.values_list("id", flat=True)
        items = Item.objects.filter(project__id__in=projects).values_list(
            "id", flat=True
        )
        assets = Asset.objects.filter(item__id__in=items).values_list("id", flat=True)
        transcriptions = Transcription.objects.filter(asset__id__in=assets)

        model_count = {
            "project": len(projects),
            "item": len(items),
            "asset": len(assets),
            "transcription": transcriptions.count(),
        }

        if request.POST:
            # This means the user confirmed the retirement
            obj_display = str(campaign)
            self.log_retirement(request, campaign, obj_display)
            progress = retire_campaign(campaign.id)
            self.message_user(
                request,
                'The retirement process for %(name)s "%(obj)s" has begun.'
                % {
                    "name": self.opts.verbose_name,
                    "obj": obj_display,
                },
                messages.SUCCESS,
            )
            post_url = reverse(
                "admin:concordia_campaignretirementprogress_change",
                args=[progress.id],
                current_app=self.admin_site.name,
            )
            return HttpResponseRedirect(post_url)

        context = {
            **self.admin_site.each_context(request),
            "title": "Are you sure?",
            "subtitle": None,
            "object_name": "Campaign",
            "object": campaign,
            "model_count": model_count.items(),
            "opts": self.opts,
            "app_label": self.opts.app_label,
            "preserved_filters": self.get_preserved_filters(request),
        }

        return TemplateResponse(
            request, "admin/concordia/campaign/retire.html", context
        )

    def log_retirement(self, request, obj, object_repr):
        return LogEntry.objects.log_action(
            user_id=request.user.pk,
            content_type_id=get_content_type_for_model(obj).pk,
            object_id=obj.pk,
            object_repr=object_repr,
            action_flag=CHANGE,
        )


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin, CustomListDisplayFieldsMixin):
    list_display = ("campaign", "topic", "sequence", "title", "resource_url")
    list_display_links = ("campaign", "topic", "sequence", "title")
    list_filter = (
        "resource_type",
        ResourceCampaignStatusListFilter,
        ResourceCampaignListFilter,
        "title",
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "campaign":
            kwargs["queryset"] = Campaign.objects.order_by("title")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(ResourceFile)
class ResourceFileAdmin(admin.ModelAdmin):
    # Bulk delete bypasses file deletion, so we don't want any bulk actions
    actions = None
    list_display = ("name", "resource_url", "updated_on")
    readonly_fields = ("resource_url", "updated_on")

    def resource_url(self, obj):
        # Boto3 adds a querystring parameters to the URL to allow access
        # to private files. In this case, all files are public, and we
        # we don't want the querystring, so we remove it.
        # This looks hacky, but seems to be the least hacky way to do
        # this without a third-party library.
        return obj.resource.url.split("?")[0]

    def get_fields(self, request, obj=None):
        # We want don't want to display the resource field except during
        # creation, since uploading a new file will leave behind the original
        # as an orphan.
        if obj:
            return (
                "name",
                "resource_url",
                "resource",
                "updated_on",
            )
        return ("name", "resource")


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    form = BleachedDescriptionAdminForm

    list_display = (
        "id",
        "title",
        "slug",
        "short_description",
        "published",
        "unlisted",
        "ordering",
    )

    list_display_links = ("id", "title", "slug")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin, CustomListDisplayFieldsMixin):
    form = BleachedDescriptionAdminForm

    # todo: add foreignKey link for campaign
    list_display = ("id", "title", "slug", "campaign", "published", "ordering")
    list_editable = ("ordering",)
    list_display_links = ("id", "title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ["title", "campaign__title"]
    list_filter = (
        "published",
        "topics",
        ProjectCampaignStatusListFilter,
        ProjectCampaignListFilter,
    )

    actions = (publish_action, unpublish_action)

    def lookup_allowed(self, key, value):
        if key in ("campaign__id__exact"):
            return True
        else:
            return super().lookup_allowed(key, value)

    def get_urls(self):
        urls = super().get_urls()

        app_label = self.model._meta.app_label
        model_name = self.model._meta.model_name

        custom_urls = [
            path(
                "<path:object_id>/item-import/",
                self.admin_site.admin_view(self.item_import_view),
                name=f"{app_label}_{model_name}_item-import",
            )
        ]

        return custom_urls + urls

    @method_decorator(permission_required("concordia.add_campaign"))
    @method_decorator(permission_required("concordia.change_campaign"))
    @method_decorator(permission_required("concordia.add_project"))
    @method_decorator(permission_required("concordia.change_project"))
    @method_decorator(permission_required("concordia.add_item"))
    @method_decorator(permission_required("concordia.change_item"))
    def item_import_view(self, request, object_id):
        project = get_object_or_404(Project, pk=object_id)

        if request.method == "POST":
            form = AdminItemImportForm(request.POST)

            if form.is_valid():
                import_url = form.cleaned_data["import_url"]

                import_job = import_items_into_project_from_url(
                    request.user, project, import_url
                )
        else:
            form = AdminItemImportForm()
            import_job = None

        media = self.media

        context = {
            **self.admin_site.each_context(request),
            "app_label": self.model._meta.app_label,
            "add": False,
            "change": False,
            "save_as": False,
            "save_on_top": False,
            "opts": self.model._meta,
            "title": f"Import Items into “{project.title}”",
            "object_id": object_id,
            "original": project,
            "media": media,
            "preserved_filters": self.get_preserved_filters(request),
            "is_popup": False,
            "has_view_permission": True,
            "has_add_permission": True,
            "has_change_permission": True,
            "has_delete_permission": False,
            "has_editable_inline_admin_formsets": False,
            "project": project,
            "form": form,
            "import_job": import_job,
        }

        return render(request, "admin/concordia/project/item_import.html", context)


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("title", "item_id", "campaign_title", "project", "published")
    list_display_links = ("title", "item_id")
    search_fields = [
        "title",
        "item_id",
        "item_url",
        "project__campaign__title",
        "project__title",
    ]

    list_filter = (
        "published",
        "project__topics",
        ItemCampaignStatusListFilter,
        ItemCampaignListFilter,
        ItemProjectListFilter2,
    )

    actions = (publish_item_action, unpublish_item_action)

    def lookup_allowed(self, key, value):
        if key in ("project__campaign__id__exact"):
            return True
        else:
            return super().lookup_allowed(key, value)

    def get_deleted_objects(self, objs, request):
        if len(objs) < 30:
            deleted_objects = [str(obj) for obj in objs]
        else:
            deleted_objects = [str(obj) for obj in objs[:3]]
            deleted_objects.append(
                f"… and {len(objs) - 3} more {Item._meta.verbose_name_plural}"
            )
        perms_needed = set()
        for model in (Item, Asset, Transcription):
            perm = "%s.%s" % (
                model._meta.app_label,
                get_permission_codename("delete", model._meta),
            )
            if not request.user.has_perm(perm):
                perms_needed.add(model._meta.verbose_name)
        protected = []

        model_count = {
            Item._meta.verbose_name_plural: len(objs),
            Asset._meta.verbose_name_plural: Asset.objects.filter(
                item__in=objs
            ).count(),
            Transcription._meta.verbose_name_plural: Transcription.objects.filter(
                asset__item__in=objs
            ).count(),
        }

        return (deleted_objects, model_count, perms_needed, protected)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("project", "project__campaign")
        return qs

    def campaign_title(self, obj):
        return obj.project.campaign.title


@admin.register(AssetTranscriptionReservation)
class AssetTranscriptionReservationAdmin(
    admin.ModelAdmin, CustomListDisplayFieldsMixin
):
    list_display = (
        "created_on",
        "updated_on",
        "asset",
        "reservation_token",
        "tombstoned",
    )
    list_display_links = ("reservation_token", "created_on")
    readonly_fields = ("asset", "created_on", "updated_on")


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin, CustomListDisplayFieldsMixin):
    list_display = (
        "published",
        "transcription_status",
        "item_id",
        "year",
        "sequence",
        "difficulty",
        "truncated_media_url",
        "media_type",
        "truncated_metadata",
    )
    list_display_links = ("item_id", "sequence")
    prepopulated_fields = {"slug": ("title",)}
    search_fields = [
        "title",
        "media_url",
        "item__project__campaign__title",
        "item__project__title",
        "item__item_id",
    ]
    list_filter = (
        "transcription_status",
        "published",
        "item__project__topics",
        AssetCampaignStatusListFilter,
        AssetCampaignListFilter,
        AssetProjectListFilter2,
        "media_type",
    )
    actions = (
        publish_action,
        change_status_to_completed,
        change_status_to_in_progress,
        change_status_to_needs_review,
        unpublish_action,
        export_to_csv_action,
        export_to_excel_action,
    )
    autocomplete_fields = ("item",)
    ordering = ("item__item_id", "sequence")
    change_list_template = "admin/concordia/asset/change_list.html"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("item").order_by("item__item_id", "sequence")

    def lookup_allowed(self, key, value):
        if key in ("item__project__id__exact", "item__project__campaign__id__exact"):
            return True
        else:
            return super().lookup_allowed(key, value)

    def item_id(self, obj):
        return obj.item.item_id

    @admin.display(description="Media URL")
    def truncated_media_url(self, obj):
        return format_html(
            '<a target="_blank" href="{}">{}</a>',
            urljoin(settings.MEDIA_URL, obj.media_url),
            truncatechars(obj.media_url, 100),
        )

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ("item",)
        return self.readonly_fields

    def change_view(self, request, object_id, extra_context=None, **kwargs):
        if object_id:
            if extra_context is None:
                extra_context = {}
            extra_context["transcriptions"] = (
                Transcription.objects.filter(asset__pk=object_id)
                .select_related("user", "reviewed_by")
                .order_by("-pk")
            )
        return super().change_view(
            request, object_id, extra_context=extra_context, **kwargs
        )

    def has_reopen_permission(self, request):
        opts = self.opts
        codename = get_permission_codename("reopen", opts)
        return request.user.has_perm(f"{opts.app_label}.{codename}")


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("id", "value")
    list_display_links = ("id", "value")
    list_filter = (TagCampaignStatusListFilter, TagCampaignListFilter)

    search_fields = ["value"]

    actions = ("export_tags_as_csv",)

    def lookup_allowed(self, key, value):
        if key in ["userassettagcollection__asset__item__project__campaign__id__exact"]:
            return True
        return super().lookup_allowed(key, value)

    def export_tags_as_csv(self, request, queryset):
        tags = queryset.prefetch_related(
            "userassettagcollection", "userassettagcollection__asset"
        ).order_by("userassettagcollection__asset_id")

        headers, data = flatten_queryset(
            tags,
            field_names=[
                "value",
                "userassettagcollection__created_on",
                "userassettagcollection__user_id",
                "userassettagcollection__asset_id",
                "userassettagcollection__asset__title",
                "userassettagcollection__asset__download_url",
                "userassettagcollection__asset__resource_url",
                "userassettagcollection__asset__item__project__campaign__slug",
            ],
            extra_verbose_names={
                "value": "tag value",
                "userassettagcollection__created_on": "user asset tag collection date created",  # noqa: E501
                "userassettagcollection__user_id": "user asset tag collection user_id",
                "userassettagcollection__asset_id": "asset id",
                "userassettagcollection__asset__title": "asset title",
                "userassettagcollection__asset__download_url": "asset download url",
                "userassettagcollection__asset__resource_url": "asset resource url",
                "userassettagcollection__asset__item__project__campaign__slug": "campaign slug",  # noqa: E501
            },
        )

        return export_to_csv_response("tags.csv", headers, data)


@admin.register(UserAssetTagCollection)
class UserAssetTagCollectionAdmin(admin.ModelAdmin):
    list_display = ("id", "asset", "user", "created_on", "updated_on")
    list_display_links = ("id", "asset")
    date_hierarchy = "created_on"
    search_fields = ["asset__title", "asset__campaign__title", "asset__project__title"]
    list_filter = (
        UserAssetTagCollectionCampaignStatusListFilter,
        "asset__item__project__campaign",
        "asset__item__project",
        "user__is_staff",
    )


@admin.register(Transcription)
class TranscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "asset",
        "user",
        "truncated_text",
        "created_on",
        "updated_on",
        "accepted",
        "rejected",
    )
    list_display_links = ("id", "asset")

    list_filter = (
        SubmittedFilter,
        AcceptedFilter,
        RejectedFilter,
        TranscriptionCampaignStatusListFilter,
        TranscriptionCampaignListFilter,
        TranscriptionProjectListFilter,
    )

    search_fields = ["text", "user__username", "user__email"]

    readonly_fields = (
        "asset",
        "user",
        "created_on",
        "updated_on",
        "submitted",
        "accepted",
        "rejected",
        "reviewed_by",
        "supersedes",
        "text",
    )

    EXPORT_FIELDS = (
        "id",
        "asset__id",
        "asset__slug",
        "user",
        "created_on",
        "updated_on",
        "supersedes",
        "submitted",
        "accepted",
        "rejected",
        "reviewed_by",
        "text",
    )

    def lookup_allowed(self, key, value):
        if key in ("asset__item__project__campaign__id__exact"):
            return True
        else:
            return super().lookup_allowed(key, value)

    @admin.display(description="Text")
    def truncated_text(self, obj):
        return truncatechars(obj.text, 100)

    def export_to_csv(self, request, queryset):
        return export_to_csv_action(
            self, request, queryset, field_names=self.EXPORT_FIELDS
        )

    def export_to_excel(self, request, queryset):
        return export_to_excel_action(
            self, request, queryset, field_names=self.EXPORT_FIELDS
        )

    actions = (export_to_csv, export_to_excel)


@admin.register(SimpleContentBlock)
class SimpleContentBlockAdmin(admin.ModelAdmin):
    form = SimpleContentBlockAdminForm

    list_display = ("slug", "created_on", "updated_on")
    readonly_fields = ("created_on", "updated_on")

    fieldsets = (
        (None, {"fields": ("created_on", "updated_on", "slug")}),
        ("Body", {"classes": ("markdown-preview",), "fields": ("body",)}),
    )


@admin.register(CarouselSlide)
class CarouselSlideAdmin(admin.ModelAdmin):
    list_display = ("headline", "published", "ordering")
    readonly_fields = ("created_on", "updated_on")


@admin.register(SimplePage)
class SimplePageAdmin(admin.ModelAdmin):
    list_display = ("path", "title", "created_on", "updated_on")
    readonly_fields = ("created_on", "updated_on")

    fieldsets = (
        (None, {"fields": ("created_on", "updated_on", "path", "title")}),
        ("Body", {"classes": ("markdown-preview",), "fields": ("body",)}),
    )


@admin.register(SiteReport)
class SiteReportAdmin(admin.ModelAdmin):
    list_display = ("created_on", "report_name", "campaign", "topic")

    list_filter = (
        "report_name",
        SiteReportSortedCampaignListFilter,
        SiteReportCampaignListFilter,
        "topic",
    )

    def export_to_csv(self, request, queryset):
        return export_to_csv_action(
            self, request, queryset, field_names=SiteReport.DEFAULT_EXPORT_FIELDNAMES
        )

    def export_to_excel(self, request, queryset):
        return export_to_excel_action(
            self, request, queryset, field_names=SiteReport.DEFAULT_EXPORT_FIELDNAMES
        )

    actions = (export_to_csv, export_to_excel)

    FIELDNAME_SORT_KEYS = [
        "created",
        "user",
        "campaign",
        "topic",
        "project",
        "item",
        "asset",
        "transcription",
        "tag",
    ]

    def fieldname_sort_key(self, key):
        for i, prefix in enumerate(self.FIELDNAME_SORT_KEYS):
            if prefix in key:
                return (i, key)
        else:
            return (1024, key)


@admin.register(UserRetiredCampaign)
class UserRetiredCampaignAdmin(admin.ModelAdmin):
    list_display = ("id", "asset_count")
    raw_id_fields = ["user", "campaign"]
    read_only_fields = (
        "user",
        "campaign",
        "asset_count",
        "asset_tag_count",
        "transcribe_count",
        "review_count",
    )


@admin.register(UserProfileActivity)
class UserProfileActivityAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "campaign",
        "get_status",
        "transcribe_count",
        "review_count",
    )
    list_filter = (
        UserProfileActivityCampaignStatusListFilter,
        UserProfileActivityCampaignListFilter,
    )
    raw_id_fields = ["user", "campaign"]
    read_only_fields = (
        "user",
        "campaign",
        "asset_count",
        "asset_tag_count",
        "transcribe_count",
        "review_count",
    )
    search_fields = [
        "user__username",
    ]


@admin.register(CampaignRetirementProgress)
class CampaignRetirementProgressAdmin(admin.ModelAdmin):
    list_display = ("campaign", "started_on", "complete", "completed_on")
    readonly_fields = (
        "campaign",
        "completion",
        "projects_removed",
        "project_total",
        "items_removed",
        "item_total",
        "assets_removed",
        "asset_total",
        "complete",
        "started_on",
        "completed_on",
        "removal_log",
    )
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "campaign",
                    "completion",
                    "projects_removed",
                    "project_total",
                    "items_removed",
                    "item_total",
                    "assets_removed",
                    "asset_total",
                    "complete",
                    "started_on",
                    "completed_on",
                ),
            },
        ),
        (
            "Log",
            {
                "fields": ("removal_log",),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Completion percentage")
    def completion(self, obj):
        if obj.complete:
            return "100%"
        total = obj.project_total + obj.item_total + obj.asset_total
        removed = obj.projects_removed + obj.items_removed + obj.assets_removed
        return "{}%".format(round(removed / total * 100, 2))
