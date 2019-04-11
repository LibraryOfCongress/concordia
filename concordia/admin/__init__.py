from urllib.parse import urljoin

from django.conf import settings
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.models import User
from django.db.models import Count
from django.shortcuts import get_object_or_404, render
from django.template.defaultfilters import truncatechars
from django.urls import path
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from tabular_export.admin import export_to_csv_action, export_to_excel_action

from exporter import views as exporter_views
from importer.tasks import import_items_into_project_from_url

from ..forms import AdminItemImportForm
from ..models import (
    Asset,
    Campaign,
    Item,
    Project,
    Resource,
    SimplePage,
    SiteReport,
    Tag,
    Theme,
    Transcription,
    UserAssetTagCollection,
)
from ..views import ReportCampaignView
from .actions import (
    publish_action,
    publish_item_action,
    reopen_asset_action,
    unpublish_action,
    unpublish_item_action,
)
from .filters import AcceptedFilter, RejectedFilter, SubmittedFilter


class ConcordiaUserAdmin(UserAdmin):
    list_display = UserAdmin.list_display + ("date_joined", "transcription_count")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.annotate(Count("transcription"))
        return qs

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

    transcription_count.admin_order_field = "transcription__count"
    actions = (export_users_as_csv, export_users_as_excel)


admin.site.unregister(User)
admin.site.register(User, ConcordiaUserAdmin)


class CustomListDisplayFieldsMixin:
    """
    Mixin which provides some custom text formatters for list display fields
    used on multiple models
    """

    def truncated_description(self, obj):
        return truncatechars(obj.description, 200)

    truncated_description.short_description = "Description"

    def truncated_metadata(self, obj):
        if obj.metadata:
            return format_html("<code>{}</code>", truncatechars(obj.metadata, 200))
        else:
            return ""

    truncated_metadata.allow_tags = True
    truncated_metadata.short_description = "Metadata"


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin, CustomListDisplayFieldsMixin):
    list_display = (
        "title",
        "short_description",
        "published",
        "display_on_homepage",
        "ordering",
        "truncated_metadata",
    )
    list_editable = ("display_on_homepage", "ordering", "published")
    list_display_links = ("title",)
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ["title", "description"]
    list_filter = ("published", "display_on_homepage")

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
        ]

        return custom_urls + urls


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin, CustomListDisplayFieldsMixin):
    list_display = ("campaign", "theme", "sequence", "title", "resource_url")
    list_display_links = ("campaign", "theme", "sequence", "title")


@admin.register(Theme)
class ThemeAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "slug")
    list_display_links = ("id", "title", "slug")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin, CustomListDisplayFieldsMixin):
    # todo: add foreignKey link for campaign
    list_display = ("id", "title", "slug", "campaign", "published")

    list_display_links = ("id", "title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ["title", "campaign__title"]
    list_filter = ("published", "campaign")

    actions = (publish_action, unpublish_action)

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
    list_filter = ("published", "project__campaign", "project")

    actions = (publish_item_action, unpublish_item_action)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("project", "project__campaign")
        return qs

    def campaign_title(self, obj):
        return obj.project.campaign.title


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
        "published",
        "item__project__campaign",
        "item__project",
        "media_type",
        "transcription_status",
    )
    actions = (publish_action, reopen_asset_action, unpublish_action)
    autocomplete_fields = ("item",)
    ordering = ("item__item_id", "sequence")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("item").order_by("item__item_id", "sequence")

    def item_id(self, obj):
        return obj.item.item_id

    def truncated_media_url(self, obj):
        return format_html(
            '<a target="_blank" href="{}">{}</a>',
            urljoin(settings.MEDIA_URL, obj.media_url),
            truncatechars(obj.media_url, 100),
        )

    truncated_media_url.allow_tags = True
    truncated_media_url.short_description = "Media URL"

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


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("id", "value")
    list_display_links = ("id", "value")

    search_fields = ["value"]


@admin.register(UserAssetTagCollection)
class UserAssetTagCollectionAdmin(admin.ModelAdmin):
    list_display = ("id", "asset", "user", "created_on", "updated_on")
    list_display_links = ("id", "asset")
    date_hierarchy = "created_on"
    search_fields = ["asset__title", "asset__campaign__title", "asset__project__title"]
    list_filter = (
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
        "asset__item__project__campaign",
        "asset__item__project",
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

    def truncated_text(self, obj):
        return truncatechars(obj.text, 100)

    truncated_text.short_description = "Text"


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
    list_display = ("created_on", "campaign")

    list_filter = ("campaign",)

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
