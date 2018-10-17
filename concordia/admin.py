import re
from urllib.parse import urljoin

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.shortcuts import get_object_or_404, render
from django.template.defaultfilters import slugify, truncatechars
from django.urls import path
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.views.decorators.cache import never_cache
from django.core.exceptions import ValidationError

from exporter import views as exporter_views
from importer.tasks import import_items_into_project_from_url
from importer.utils.excel import slurp_excel

from .forms import AdminItemImportForm, AdminProjectBulkImportForm
from .models import (
    Asset,
    Campaign,
    Item,
    Project,
    Resource,
    Tag,
    Transcription,
    UserAssetTagCollection,
)
from .views import ReportCampaignView


def publish_item_action(modeladmin, request, queryset):
    """
    Mark all of the selected items and their related assets as published
    """

    count = queryset.filter(published=False).update(published=True)
    asset_count = Asset.objects.filter(item__in=queryset, published=False).update(
        published=True
    )

    messages.add_message(
        request, messages.INFO, f"Published {count} items and {asset_count} assets"
    )


publish_item_action.short_description = "Publish selected items and assets"


def unpublish_item_action(modeladmin, request, queryset):
    """
    Mark all of the selected items and their related assets as unpublished
    """

    count = queryset.filter(published=True).update(published=False)
    asset_count = Asset.objects.filter(item__in=queryset, published=True).update(
        published=False
    )

    messages.add_message(
        request, messages.INFO, f"Unpublished {count} items and {asset_count} assets"
    )


unpublish_item_action.short_description = "Unpublish selected items and assets"


def publish_action(modeladmin, request, queryset):
    """
    Mark all of the selected objects as published
    """

    count = queryset.filter(published=False).update(published=True)
    messages.add_message(request, messages.INFO, f"Published {count} objects")


publish_action.short_description = "Publish selected"


def unpublish_action(modeladmin, request, queryset):
    """
    Mark all of the selected objects as unpublished
    """

    count = queryset.filter(published=True).update(published=False)
    messages.add_message(request, messages.INFO, f"Unpublished {count} objects")


unpublish_action.short_description = "Unpublish selected"


def campaign_get_or_create(campaign_title, row):
    created = False
    try:
        campaign = Campaign.objects.get(title=campaign_title)
    except Campaign.DoesNotExist:
        campaign = Campaign(
            title=campaign_title,
            slug=slugify(campaign_title),
            description=row["Campaign Long Description"] or "",
            short_description=row["Campaign Short Description"] or "",
        )
        campaign.full_clean()
        campaign.save()
        created = True
    return campaign, created


def project_get_or_create(project_title, campaign, row):
    created = False
    try:
        project = campaign.project_set.get(title=project_title)
    except Project.DoesNotExist:
        project = Project(
            title=project_title,
            slug=slugify(project_title),
            description=row["Project Description"] or "",
            campaign=campaign,
        )
        project.full_clean()
        project.save()
        created = True
    return project, created


@never_cache
@staff_member_required
@permission_required("concordia.add_campaign")
@permission_required("concordia.change_campaign")
@permission_required("concordia.add_project")
@permission_required("concordia.change_project")
@permission_required("concordia.add_item")
@permission_required("concordia.change_item")
def admin_bulk_import_view(request):
    # TODO: when we upgrade to Django 2.1 we can use the admin site override
    # mechanism (the old one is broken in 2.0): see
    # https://code.djangoproject.com/ticket/27887 in the meantime, this will
    # simply be a regular Django view using forms and just enough context to
    # reuse the Django admin template

    request.current_app = "admin"

    context = {"title": "Bulk Import"}

    if request.method == "POST":
        form = AdminProjectBulkImportForm(request.POST, request.FILES)

        if form.is_valid():
            context["import_jobs"] = import_jobs = []

            rows = slurp_excel(request.FILES["spreadsheet_file"])
            required_fields = [
                "Campaign",
                "Campaign Short Description",
                "Campaign Long Description",
                "Project",
                "Project Description",
                "Import URLs",
            ]
            for idx, row in enumerate(rows):
                missing_fields = [i for i in required_fields if i not in row]
                if missing_fields:
                    messages.add_message(
                        request,
                        messages.WARNING,
                        f"Skipping row {idx}: missing fields {missing_fields}",
                    )
                    continue

                campaign_title = row["Campaign"]
                project_title = row["Project"]
                import_url_blob = row["Import URLs"]

                if not all((campaign_title, project_title, import_url_blob)):
                    warning_message = (
                        f"Skipping row {idx}: at least one required field "
                        "(Campaign, Project, Import URLs) is empty",
                    )
                    messages.add_message(request, messages.WARNING, warning_message)
                    continue

                try:
                    campaign, created = campaign_get_or_create(campaign_title, row)
                except ValidationError:
                    messages.add_message(
                        request,
                        messages.ERROR,
                        f"Validation error occurred creating campaign {campaign_title}",
                    )

                if created:
                    messages.add_message(
                        request, messages.INFO, f"Created new campaign {campaign_title}"
                    )
                else:
                    messages.add_message(
                        request,
                        messages.INFO,
                        f"Reusing campaign {campaign_title} without modification",
                    )

                try:
                    project, created = project_get_or_create(
                        project_title, campaign, row
                    )
                except ValidationError:
                    messages.add_message(
                        request,
                        messages.ERROR,
                        f"Validation error occurred creating project {project_title}",
                    )

                if created:
                    messages.add_message(
                        request, messages.INFO, f"Created new project {project_title}"
                    )
                else:
                    messages.add_message(
                        request,
                        messages.INFO,
                        f"Reusing project {project_title} without modification",
                    )

                potential_urls = filter(None, re.split(r"[\s]+", import_url_blob))
                for url in potential_urls:
                    if not url.startswith("http"):
                        continue
                    import_jobs.append(
                        import_items_into_project_from_url(request.user, project, url)
                    )
                    messages.add_message(
                        request,
                        messages.INFO,
                        f"Queued {campaign_title} {project_title} import for {url}",
                    )
    else:
        form = AdminProjectBulkImportForm()

    context["form"] = form

    return render(request, "admin/bulk_import.html", context)


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
        "short_description",
        "start_date",
        "end_date",
        "truncated_metadata",
        "published",
    )
    list_display_links = ("id", "title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ["title", "description"]
    list_filter = ("published",)

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
                exporter_views.ExportCampaignToBagit.as_view(),
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
    list_display = ("campaign", "sequence", "title", "resource_url")


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
        "published",
    )

    list_display_links = ("id", "title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ["title", "campaign__title"]
    list_filter = ("published", "category", "campaign")

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

    readonly_fields = ("project",)

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
        "sequence",
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
    actions = (publish_action, unpublish_action)

    readonly_fields = ("item",)

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

    search_fields = ["text"]

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
