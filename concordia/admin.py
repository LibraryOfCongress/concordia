from urllib.parse import urljoin

from django.conf import settings
from django.contrib import admin
from django.contrib.auth.decorators import permission_required
from django.shortcuts import get_object_or_404, render
from django.template.defaultfilters import truncatechars
from django.urls import path
from django.utils.decorators import method_decorator
from django.utils.html import format_html

from importer.tasks import import_items_into_project_from_url

from .forms import AdminItemImportForm
from .models import (
    Asset,
    Campaign,
    Item,
    Project,
    Tag,
    Transcription,
    UserAssetTagCollection,
)


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
        "id",
        "title",
        "slug",
        "truncated_description",
        "start_date",
        "end_date",
        "truncated_metadata",
        "is_active",
        "s3_storage",
        "status",
    )
    list_display_links = ("id", "title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ["title", "description"]
    list_filter = ("status", "is_active")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin, CustomListDisplayFieldsMixin):
    # todo: add foreignKey link for campaign
    list_display = (
        "id",
        "title",
        "slug",
        "category",
        "campaign",
        "truncated_metadata",
        "status",
    )

    list_display_links = ("id", "title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ["title", "campaign__title"]
    list_filter = ("status", "category", "campaign")

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

                task_id = import_items_into_project_from_url(project, import_url)
        else:
            form = AdminItemImportForm()
            task_id = None

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
            "task_id": task_id,
        }

        return render(request, "admin/concordia/project/item_import.html", context)


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "slug",
        "item_id",
        "campaign",
        "project",
        "status",
        "is_publish",
    )
    list_display_links = ("title", "slug", "item_id")
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ["title", "campaign__title", "project__title"]
    list_filter = ("status", "campaign")


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin, CustomListDisplayFieldsMixin):
    list_display = (
        "id",
        "title",
        "slug",
        "truncated_description",
        "truncated_media_url",
        "media_type",
        "campaign",
        "project",
        "sequence",
        "truncated_metadata",
        "status",
    )
    list_display_links = ("id", "title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ["title", "media_url", "campaign__title", "project__title"]
    list_filter = ("status", "campaign", "project", "media_type")

    def truncated_media_url(self, obj):
        return format_html(
            '<a target="_blank" href="{}">{}</a>',
            urljoin(settings.MEDIA_URL, obj.media_url),
            truncatechars(obj.media_url, 100),
        )

    truncated_media_url.allow_tags = True
    truncated_media_url.short_description = "Media URL"


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "value")
    list_display_links = ("id", "name", "value")

    search_fields = ["name", "value"]


@admin.register(UserAssetTagCollection)
class UserAssetTagCollectionAdmin(admin.ModelAdmin):
    list_display = ("id", "asset", "user_id", "created_on", "updated_on")
    list_display_links = ("id", "asset")
    date_hierarchy = "created_on"
    search_fields = ["asset__title", "asset__campaign__title", "asset__project__title"]
    # FIXME: after fixing the user_id relationship add filtering on user attributes


@admin.register(Transcription)
class TranscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "asset",
        "parent",
        "user_id",
        "truncated_text",
        "status",
        "created_on",
        "updated_on",
    )
    list_display_links = ("id", "asset")

    list_filter = ("status",)

    search_fields = ["text"]

    def truncated_text(self, obj):
        return truncatechars(obj.text, 100)

    truncated_text.short_description = "Text"
