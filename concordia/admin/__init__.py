import io
import logging
import zipfile
from typing import Any

from django.contrib import admin, messages
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.admin.options import get_content_type_for_model
from django.contrib.auth import get_permission_codename
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.models import User
from django.db.models import Exists, OuterRef, QuerySet
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.template.defaultfilters import truncatechars
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_protect

from exporter import views as exporter_views
from exporter.tabular_export.admin import export_to_csv_action, export_to_excel_action
from exporter.tabular_export.core import export_to_csv_response, flatten_queryset
from importer.tasks.items import import_items_into_project_from_url

from ..models import (
    Asset,
    AssetTranscriptionReservation,
    Banner,
    Campaign,
    CampaignRetirementProgress,
    Card,
    CardFamily,
    CarouselSlide,
    Guide,
    Item,
    KeyMetricsReport,
    NextReviewableCampaignAsset,
    NextReviewableTopicAsset,
    NextTranscribableCampaignAsset,
    NextTranscribableTopicAsset,
    Project,
    ProjectTopic,
    Resource,
    ResourceFile,
    SimplePage,
    SiteReport,
    Tag,
    Topic,
    Transcription,
    TutorialCard,
    UserAssetTagCollection,
    UserProfileActivity,
)
from ..tasks.retirement import retire_campaign
from ..views.campaigns import ReportCampaignView
from .actions import (
    anonymize_action,
    change_status_to_completed,
    change_status_to_in_progress,
    change_status_to_needs_review,
    publish_action,
    publish_item_action,
    unpublish_action,
    unpublish_item_action,
    verify_assets_action,
)
from .filters import (
    AcceptedFilter,
    AssetCampaignListFilter,
    AssetCampaignStatusListFilter,
    AssetProjectListFilter,
    CardCampaignListFilter,
    ItemCampaignListFilter,
    ItemCampaignStatusListFilter,
    ItemProjectListFilter,
    NextAssetCampaignListFilter,
    OcrGeneratedFilter,
    OcrOriginatedFilter,
    ProjectCampaignListFilter,
    ProjectCampaignStatusListFilter,
    RejectedFilter,
    ResourceCampaignListFilter,
    ResourceCampaignStatusListFilter,
    SiteReportCampaignListFilter,
    SiteReportSortedCampaignListFilter,
    SubmittedFilter,
    SupersededListFilter,
    TagCampaignListFilter,
    TagCampaignStatusListFilter,
    TopicListFilter,
    TranscriptionCampaignListFilter,
    TranscriptionCampaignStatusListFilter,
    TranscriptionProjectListFilter,
    UserAssetTagCollectionCampaignListFilter,
    UserAssetTagCollectionCampaignStatusListFilter,
    UserProfileActivityCampaignListFilter,
    UserProfileActivityCampaignStatusListFilter,
)
from .forms import (
    AdminItemImportForm,
    AssetStatusActionForm,
    CampaignAdminForm,
    CardAdminForm,
    GuideAdminForm,
    ItemAdminForm,
    KeyMetricsReportAdminForm,
    ProjectAdminForm,
    ProjectTopicInlineForm,
    TopicAdminForm,
)

logger = logging.getLogger(__name__)


class ConcordiaUserAdmin(UserAdmin):
    """
    Customize the Django admin for `User` objects.

    Adds transcription and review counters to the changelist and provides
    CSV and Excel export actions.
    """

    list_display = (
        "username",
        "email",
        "is_staff",
        "date_joined",
        "transcription_count",
        "review_count",
    )

    def get_queryset(
        self,
        request: HttpRequest,
    ) -> QuerySet[User]:
        """
        Build the queryset used for the user changelist.

        Adds a `select_related` on the related profile to reduce per-row
        database queries when rendering counts.

        Args:
            request (HttpRequest): Current admin request.

        Returns:
            QuerySet[User]: Queryset with related profiles preloaded.
        """
        qs = super().get_queryset(request).select_related("profile")
        return qs

    @admin.display(
        description="Transcription Count",
        ordering="profile__transcribe_count",
    )
    def transcription_count(self, obj: User) -> int:
        return obj.profile.transcribe_count

    @admin.display(
        description="Review Count",
        ordering="profile__review_count",
    )
    def review_count(self, obj: User) -> int:
        return obj.profile.review_count

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
        "profile__transcribe_count",
        "profile__review_count",
    )

    EXTRA_VERBOSE_NAMES = {
        "profile__transcribe_count": "transcription count",
        "profile__review_count": "review count",
    }

    def export_users_as_csv(
        self,
        request: HttpRequest,
        queryset: QuerySet[User],
    ) -> HttpResponse:
        """
        Export selected users as a CSV file.

        Args:
            request (HttpRequest): Current admin request.
            queryset (QuerySet[User]): Selected users to export.

        Returns:
            HttpResponse: Response that streams a CSV download.
        """
        return export_to_csv_action(
            self,
            request,
            queryset,
            field_names=self.EXPORT_FIELDS,
            extra_verbose_names=self.EXTRA_VERBOSE_NAMES,
        )

    def export_users_as_excel(
        self,
        request: HttpRequest,
        queryset: QuerySet[User],
    ) -> HttpResponse:
        """
        Export selected users as an Excel file.

        Args:
            request (HttpRequest): Current admin request.
            queryset (QuerySet[User]): Selected users to export.

        Returns:
            HttpResponse: Response that streams an Excel download.
        """
        return export_to_excel_action(
            self,
            request,
            queryset,
            field_names=self.EXPORT_FIELDS,
            extra_verbose_names=self.EXTRA_VERBOSE_NAMES,
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
    Provide reusable list display helpers for admin changelists.

    This mixin defines helpers that truncate long text and render selected
    fields using HTML formatting.
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
    """
    Admin configuration for `Campaign` objects.

    Adds filters, publishing actions, export links and a custom retirement
    workflow.
    """

    form = CampaignAdminForm

    list_display = (
        "title",
        "status",
        "published",
        "display_on_homepage",
        "next_transcription_campaign",
        "next_review_campaign",
        "ordering",
        "launch_date",
        "completed_date",
    )
    list_editable = (
        "display_on_homepage",
        "next_transcription_campaign",
        "next_review_campaign",
        "ordering",
        "published",
        "unlisted",
        "status",
        "launch_date",
        "completed_date",
    )
    list_display_links = ("title",)
    fields = (
        "published",
        "unlisted",
        "status",
        "next_transcription_campaign",
        "next_review_campaign",
        "ordering",
        "display_on_homepage",
        "title",
        "slug",
        "card_family",
        "thumbnail_image",
        "image_alt_text",
        "launch_date",
        "completed_date",
        "description",
        "short_description",
        "metadata",
        "disable_ocr",
        "research_centers",
    )
    prepopulated_fields = {"slug": ("title",)}
    raw_id_fields = ("card_family",)
    search_fields = ["title", "description"]
    list_filter = (
        "published",
        "display_on_homepage",
        "unlisted",
        "status",
        "next_transcription_campaign",
        "next_review_campaign",
    )

    actions = (publish_action, unpublish_action, verify_assets_action)

    def get_form(
        self,
        request: HttpRequest,
        obj: Campaign | None = None,
        **kwargs: Any,
    ):
        """
        Build the model form used to edit a campaign.

        Updates some field labels to be clearer for staff users before
        returning the base form from `ModelAdmin`.

        Args:
            request (HttpRequest): Current admin request.
            obj (Campaign | None): Campaign being edited, or `None` when
                creating a new one.
            **kwargs (Any): Extra keyword arguments passed to
                `ModelAdmin.get_form`.

        Returns:
            forms.ModelForm: Form class used by the admin for this model.
        """
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["display_on_homepage"].label = "Display on homepage"
        form.base_fields["next_transcription_campaign"].label = (
            "Next transcription campaign"
        )
        form.base_fields["next_review_campaign"].label = "Next review campaign"
        return form

    def get_urls(self):
        """
        Add custom admin URLs for campaign exports, reports and retirement.

        Returns:
            list: List of URL patterns including the default admin URLs and
            the custom campaign URLs.
        """
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
    @method_decorator(
        permission_required("concordia.retire_campaign", raise_exception=True)
    )
    @method_decorator(
        permission_required("concordia.delete_project", raise_exception=True)
    )
    @method_decorator(
        permission_required("concordia.delete_item", raise_exception=True)
    )
    @method_decorator(
        permission_required("concordia.delete_asset", raise_exception=True)
    )
    @method_decorator(
        permission_required("concordia.delete_transcription", raise_exception=True)
    )
    @method_decorator(
        permission_required("concordia.delete_import_item_asset", raise_exception=True)
    )
    def retire(
        self,
        request: HttpRequest,
        campaign_slug: str,
    ) -> HttpResponse:
        """
        Start the retirement process for a campaign.

        This view shows a confirmation page that lists how many projects,
        items, assets and transcriptions will be removed. When the request
        is `POST`, it enqueues the retirement task and redirects to the
        progress object in the admin.

        Args:
            request (HttpRequest): Current admin request.
            campaign_slug (str): Slug of the campaign being retired.

        Returns:
            HttpResponse: Confirmation page or redirect to the progress
            object.
        """
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

    def log_retirement(
        self,
        request: HttpRequest,
        obj: Campaign,
        object_repr: str,
    ) -> LogEntry:
        """
        Create an admin log entry for a campaign retirement.

        Args:
            request (HttpRequest): Current admin request.
            obj (Campaign): Campaign that is being retired.
            object_repr (str): Text representation of the campaign used in
                the log entry.

        Returns:
            LogEntry: The created log entry instance.
        """
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
        TopicListFilter,
        ResourceCampaignListFilter,
    )

    def formfield_for_foreignkey(
        self,
        db_field: Any,
        request: HttpRequest,
        **kwargs: Any,
    ) -> Any:
        """
        Customize the form field for foreign key relations.

        Orders campaigns alphabetically when selecting a campaign.

        Args:
            db_field (Any): Model field being rendered.
            request (HttpRequest): Current admin request.
            **kwargs (Any): Extra keyword arguments for the base
                implementation.

        Returns:
            Any: Form field instance for the foreign key.
        """
        if db_field.name == "campaign":
            kwargs["queryset"] = Campaign.objects.order_by("title")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(ResourceFile)
class ResourceFileAdmin(admin.ModelAdmin):
    # Bulk delete bypasses file deletion, so we do not want any bulk actions
    actions = None
    list_display = ("name", "resource_url", "updated_on")
    readonly_fields = ("resource_url", "updated_on")

    def resource_url(self, obj: ResourceFile) -> str:
        """
        Return the public URL for this resource without any query string.

        Boto3 storage backends often append query parameters that are not
        needed for public files. This helper strips them so the URL is
        easier to copy and read.

        Args:
            obj (ResourceFile): Resource file instance.

        Returns:
            str: Public URL without query parameters.
        """
        # Boto3 adds querystring parameters to the URL to allow access
        # to private files. In this case, all files are public, and we
        # do not want the querystring, so we remove it.
        # This looks hacky, but seems to be the least hacky way to do
        # this without a third-party library.
        return obj.resource.url.split("?")[0]

    def get_fields(
        self,
        request: HttpRequest,
        obj: ResourceFile | None = None,
    ) -> tuple[str, ...]:
        """
        Control which fields are shown on the change and add views.

        When editing an existing object some fields are read only, but
        when creating a new one only editable fields are shown.

        Args:
            request (HttpRequest): Current admin request.
            obj (ResourceFile | None): Resource file being edited, or
                `None` when adding a new one.

        Returns:
            tuple[str, ...]: Field names to display in the form.
        """
        if obj:
            return (
                "name",
                "resource_url",
                "resource",
                "updated_on",
            )
        return ("name", "resource")


class TopicProjectInline(admin.TabularInline):
    model = ProjectTopic
    form = ProjectTopicInlineForm
    extra = 1
    autocomplete_fields = ["project"]
    fields = ["project", "url_filter", "ordering"]
    fk_name = "topic"


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    form = TopicAdminForm

    inlines = [TopicProjectInline]

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
    search_fields = [
        "title",
    ]


class ProjectTopicInline(admin.TabularInline):
    model = ProjectTopic
    form = ProjectTopicInlineForm
    extra = 1
    autocomplete_fields = ["topic"]
    fields = ["topic", "url_filter"]


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin, CustomListDisplayFieldsMixin):
    form = ProjectAdminForm

    inlines = [ProjectTopicInline]

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

    actions = (publish_action, unpublish_action, verify_assets_action)

    def lookup_allowed(self, key: str, value: str) -> bool:
        """
        Allow filtering by campaign id in the changelist.

        Args:
            key (str): Lookup parameter key.
            value (str): Lookup parameter value.

        Returns:
            bool: True if the lookup is allowed.
        """
        if key in ("campaign__id__exact"):
            return True
        else:
            return super().lookup_allowed(key, value)

    def get_urls(self):
        """
        Add custom URLs for project item import and CSV export.

        Returns:
            list: Custom URL patterns combined with the default admin URLs.
        """
        urls = super().get_urls()

        app_label = self.model._meta.app_label
        model_name = self.model._meta.model_name

        custom_urls = [
            path(
                "<path:object_id>/item-import/",
                self.admin_site.admin_view(self.item_import_view),
                name=f"{app_label}_{model_name}_item-import",
            ),
            path(
                "exportCSV/<path:campaign_slug>/<path:project_slug>/",
                exporter_views.ExportProjectToCSV.as_view(),
                name=f"{app_label}_{model_name}_export-csv",
            ),
        ]

        return custom_urls + urls

    @method_decorator(
        permission_required("concordia.add_campaign", raise_exception=True)
    )
    @method_decorator(
        permission_required("concordia.change_campaign", raise_exception=True)
    )
    @method_decorator(
        permission_required("concordia.add_project", raise_exception=True)
    )
    @method_decorator(
        permission_required("concordia.change_project", raise_exception=True)
    )
    @method_decorator(permission_required("concordia.add_item", raise_exception=True))
    @method_decorator(
        permission_required("concordia.change_item", raise_exception=True)
    )
    def item_import_view(
        self,
        request: HttpRequest,
        object_id: str,
    ) -> HttpResponse:
        """
        Display and process the admin item import form for a project.

        When the request is `GET`, this view shows a form where staff can
        paste a URL for the import. When the request is `POST` and the form
        is valid, it queues an item import job and redisplays the form with
        basic job information.

        Args:
            request (HttpRequest): Current admin request.
            object_id (str): Primary key of the project being imported
                into.

        Returns:
            HttpResponse: Rendered admin page for the import form.
        """
        project = get_object_or_404(Project, pk=object_id)

        if request.method == "POST":
            form = AdminItemImportForm(request.POST)

            if form.is_valid():
                import_url = form.cleaned_data["import_url"]

                import_job = import_items_into_project_from_url(
                    request.user, project, import_url
                )
            else:
                import_job = None
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
    form = ItemAdminForm
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
        ItemProjectListFilter,
    )

    actions = (publish_item_action, unpublish_item_action, verify_assets_action)

    def lookup_allowed(self, key: str, value: str) -> bool:
        """
        Allow filtering by campaign id in the changelist.

        Args:
            key (str): Lookup parameter key.
            value (str): Lookup parameter value.

        Returns:
            bool: True if the lookup is allowed.
        """
        if key in ("project__campaign__id__exact",):
            return True
        else:
            return super().lookup_allowed(key, value)

    def get_deleted_objects(
        self,
        objs: list[Item],
        request: HttpRequest,
    ):
        """
        Summarize the impact of deleting the given items.

        This override includes counts of related assets and transcriptions
        and enforces delete permissions for related models.

        Args:
            objs (list[Item]): Items selected for deletion.
            request (HttpRequest): Current admin request.

        Returns:
            tuple[list[str], dict[str, int], set[str], list]:
                Deleted object labels, counts per model, permissions that
                are still needed and a list of protected objects.
        """
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

    def get_queryset(
        self,
        request: HttpRequest,
    ):
        """
        Optimize the queryset used on the item changelist.

        Adds related project and campaign so list-display columns do not
        trigger extra database queries.
        """
        qs = super().get_queryset(request)
        qs = qs.select_related("project", "project__campaign")
        return qs

    def campaign_title(self, obj: Item) -> str:
        """
        Return the campaign title for the item's project.

        Args:
            obj (Item): Item instance.

        Returns:
            str: Title of the related campaign.
        """
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
        "truncated_storage_image",
        "media_type",
        "truncated_metadata",
    )
    list_display_links = ("item_id", "sequence")
    prepopulated_fields = {"slug": ("title",)}
    search_fields = [
        "title",
        "storage_image",
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
        AssetProjectListFilter,
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
        verify_assets_action,
    )
    status_action_names = (
        "change_status_to_completed",
        "change_status_to_needs_review",
        "change_status_to_in_progress",
    )
    autocomplete_fields = ("item",)
    ordering = ("item__item_id", "sequence")
    change_list_template = "admin/concordia/asset/change_list.html"

    def get_queryset(
        self,
        request: HttpRequest,
    ):
        """
        Optimize the queryset used on the asset changelist.

        Selects related items so fields displayed in the changelist do not
        trigger per-row database queries.
        """
        qs = super().get_queryset(request)
        return qs.select_related("item").order_by("item__item_id", "sequence")

    def lookup_allowed(self, key: str, value: str) -> bool:
        """
        Allow filtering by project and campaign id on the changelist.

        Args:
            key (str): Lookup parameter key.
            value (str): Lookup parameter value.

        Returns:
            bool: True if the lookup is allowed.
        """
        if key in ("item__project__id__exact", "item__project__campaign__id__exact"):
            return True
        else:
            return super().lookup_allowed(key, value)

    def response_action(
        self,
        request: HttpRequest,
        queryset: QuerySet[Asset],
    ) -> HttpResponse:
        """
        Run the selected action and optionally redirect to a `next` URL.

        After the base implementation runs the action, this override checks
        for a `next` parameter in `POST` and, if it is a safe URL, redirects
        to it instead of the default changelist.

        Args:
            request (HttpRequest): Current admin request.
            queryset (QuerySet[Asset]): Selected assets for the action.

        Returns:
            HttpResponse: Default admin response or a redirect to the
            `next` URL.
        """
        # Let Django run the chosen action(s) normally
        response = super().response_action(request, queryset)

        # If a "next" came from our form, redirect there,
        # after confirming it is either a relative path
        # that starts with "/" or is an absolute URL
        # pointing to our hostname
        next_url = request.POST.get("next")
        if next_url:
            if url_has_allowed_host_and_scheme(
                url=next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return HttpResponseRedirect(next_url)

        # Otherwise, return whatever Django gave us
        return response

    def item_id(self, obj: Asset) -> str:
        return obj.item.item_id

    @admin.display(description="Media URL")
    def truncated_storage_image(self, obj: Asset) -> str:
        return format_html(
            '<a target="_blank" href="{}">{}</a>',
            obj.storage_image.url,
            truncatechars(obj.get_existing_storage_image_filename(), 100),
        )

    def get_readonly_fields(
        self,
        request: HttpRequest,
        obj: Asset | None = None,
    ) -> tuple[str, ...]:
        """
        Mark some fields as read only after an asset has been created.

        The item and campaign cannot be changed on existing assets but
        remain editable when creating a new asset.

        Args:
            request (HttpRequest): Current admin request.
            obj (Asset | None): Asset being edited, or `None` when adding.

        Returns:
            tuple[str, ...]: Names of fields that should be read only.
        """
        if obj:
            return self.readonly_fields + ("item", "campaign")
        return self.readonly_fields

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        extra_context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> HttpResponse:
        """
        Render the asset change form with extra status and transcription data.

        This override injects a form for bulk status changes and a list of
        related transcriptions into the template context.

        Args:
            request (HttpRequest): Current admin request.
            object_id (str): Primary key of the asset being edited.
            extra_context (dict[str, Any] | None): Extra template context,
                if any.
            **kwargs (Any): Extra keyword arguments passed to the base
                implementation.

        Returns:
            HttpResponse: Response from the admin change view.
        """
        extra_context = extra_context or {}
        asset = None
        if object_id:
            asset = self.get_object(request, object_id)
            current_status = asset.transcription_status
            # Dealing with this one special case let's use simplify the
            # desired_actions filtering code here significantly
            if current_status == "submitted":
                current_status = "needs_review"
            # We need the name of the action (for example,
            # 'change_status_to_in_progress') and the description to show
            # in the form (for example, "Change status to In Progress").
            # We filter out any action matching the current status, since
            # that is unneeded and potentially confusing.
            desired_actions = [
                (name, data[2])
                for name, data in self.get_actions(request).items()
                if name in self.status_action_names and current_status not in name
            ]
            status_form = AssetStatusActionForm(available_actions=desired_actions)
            extra_context["status_action_form"] = status_form

        extra_context["transcriptions"] = (
            Transcription.objects.filter(asset__pk=object_id)
            .select_related("user", "reviewed_by")
            .order_by("-pk")
        )

        return super().change_view(
            request, object_id, extra_context=extra_context, **kwargs
        )

    def has_reopen_permission(self, request: HttpRequest) -> bool:
        """
        Check whether the user has the custom `reopen` permission.

        Args:
            request (HttpRequest): Current admin request.

        Returns:
            bool: True if the user has permission to reopen assets.
        """
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

    def lookup_allowed(self, key: str, value: str) -> bool:
        """
        Allow filtering by campaign id when viewing tags.

        Args:
            key (str): Lookup parameter key.
            value (str): Lookup parameter value.

        Returns:
            bool: True if the lookup is allowed.
        """
        if key in ["userassettagcollection__asset__item__project__campaign__id__exact"]:
            return True
        return super().lookup_allowed(key, value)

    def export_tags_as_csv(
        self,
        request: HttpRequest,
        queryset: QuerySet[Tag],
    ) -> HttpResponse:
        """
        Export tag usage details as a CSV file.

        Args:
            request (HttpRequest): Current admin request.
            queryset (QuerySet[Tag]): Selected tags to export.

        Returns:
            HttpResponse: Response that streams a CSV download.
        """
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
        UserAssetTagCollectionCampaignListFilter,
        "asset__item__project",
        "user__is_staff",
    )


@admin.register(Transcription)
class TranscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "asset",
        "user",
        "campaign_slug",
        "truncated_text",
        "created_on",
        "accepted",
        "rejected",
        "reviewed_by",
        "superseded",
    )
    list_display_links = ("id", "asset")

    list_filter = (
        SubmittedFilter,
        AcceptedFilter,
        RejectedFilter,
        SupersededListFilter,
        OcrGeneratedFilter,
        OcrOriginatedFilter,
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
        "source",
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
        "ocr_generated",
        "ocr_originated",
    )

    show_full_result_count = False

    def get_queryset(
        self,
        request: HttpRequest,
    ) -> QuerySet[Transcription]:
        """
        Optimize the queryset used on the transcription changelist.

        Selects related asset and user records and annotates a boolean flag
        so the superseded column can be rendered without extra queries.

        Args:
            request (HttpRequest): Current admin request.

        Returns:
            QuerySet[Transcription]: Optimized queryset for the changelist.
        """
        qs = super().get_queryset(request)
        # Make FK columns cheaper to render
        qs = qs.select_related("asset", "user", "reviewed_by")

        # Annotate a boolean so the "Superseded?" column is O(1) per row
        return qs.annotate(
            is_superseded=Exists(
                Transcription.objects.filter(supersedes=OuterRef("pk"))
            )
        )

    @admin.display(description="Text")
    def truncated_text(self, obj: Transcription) -> str:
        """
        Return a shortened version of the transcription text.

        Args:
            obj (Transcription): Transcription instance.

        Returns:
            str: Text truncated to a reasonable length for display.
        """
        return truncatechars(obj.text, 100)

    @admin.display(boolean=True, description="Superseded?")
    def superseded(self, obj: Transcription) -> bool:
        """
        Indicate whether this transcription has been superseded.

        Uses the `is_superseded` annotation added in `get_queryset` so the
        column can be rendered without extra queries.

        Args:
            obj (Transcription): Transcription instance.

        Returns:
            bool: True if a later transcription supersedes this one.
        """
        # Uses the annotation from get_queryset; no per-row queries.
        return bool(getattr(obj, "is_superseded", False))

    def lookup_allowed(self, key: str, value: str) -> bool:
        """
        Allow filtering by campaign id in the transcription admin.

        Args:
            key (str): Lookup parameter key.
            value (str): Lookup parameter value.

        Returns:
            bool: True if the lookup is allowed.
        """
        if key in ("asset__item__project__campaign__id__exact",):
            return True
        return super().lookup_allowed(key, value)

    def export_to_csv(
        self,
        request: HttpRequest,
        queryset: QuerySet[Transcription],
    ) -> HttpResponse:
        """
        Export selected transcriptions as a CSV file.

        Args:
            request (HttpRequest): Current admin request.
            queryset (QuerySet[Transcription]): Transcriptions to export.

        Returns:
            HttpResponse: Response that streams a CSV download.
        """
        return export_to_csv_action(
            self, request, queryset, field_names=self.EXPORT_FIELDS
        )

    def export_to_excel(
        self,
        request: HttpRequest,
        queryset: QuerySet[Transcription],
    ) -> HttpResponse:
        """
        Export selected transcriptions as an Excel file.

        Args:
            request (HttpRequest): Current admin request.
            queryset (QuerySet[Transcription]): Transcriptions to export.

        Returns:
            HttpResponse: Response that streams an Excel download.
        """
        return export_to_excel_action(
            self, request, queryset, field_names=self.EXPORT_FIELDS
        )

    actions = (export_to_csv, export_to_excel)


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
    list_display = ("created_on", "report_type")
    readonly_fields = (
        "created_on",
        "report_type",
        "previous_in_series_link",
        "next_in_series_link",
        "report_json",
    )
    fieldsets = (
        ("Summary", {"fields": ("created_on", "report_type")}),
        (
            "Navigation within series",
            {"fields": ("previous_in_series_link", "next_in_series_link")},
        ),
        (
            "Data",
            {
                "fields": (
                    "report_name",
                    "campaign",
                    "topic",
                    "assets_total",
                    "assets_published",
                    "assets_not_started",
                    "assets_in_progress",
                    "assets_waiting_review",
                    "assets_completed",
                    "assets_unpublished",
                    "assets_started",
                    "items_published",
                    "items_unpublished",
                    "projects_published",
                    "projects_unpublished",
                    "anonymous_transcriptions",
                    "transcriptions_saved",
                    "daily_review_actions",
                    "distinct_tags",
                    "tag_uses",
                    "campaigns_published",
                    "campaigns_unpublished",
                    "users_registered",
                    "users_activated",
                    "registered_contributors",
                    "daily_active_users",
                )
            },
        ),
        ("Debug", {"fields": ("report_json",)}),
    )

    list_filter = (
        "report_name",
        SiteReportSortedCampaignListFilter,
        SiteReportCampaignListFilter,
        "topic",
    )

    @admin.display(description="Report type")
    def report_type(self, obj: "SiteReport") -> str:
        """
        Describe what kind of report this SiteReport represents.

        Args:
            obj (SiteReport): Site report instance.

        Returns:
            str: Human readable description of the report source.
        """
        if obj.report_name:
            return f"Report name: {obj.report_name}"
        elif obj.campaign:
            return f"Campaign: {obj.campaign}"
        elif obj.topic:
            return f"Topic: {obj.topic}"
        else:
            return f"SiteReport: <{obj.id}>"

    @admin.display(description="SiteReport as JSON")
    def report_json(self, obj: "SiteReport") -> str:
        """
        Render a pretty printed JSON representation of this report.

        Args:
            obj (SiteReport): Site report instance.

        Returns:
            str: HTML snippet that shows the report JSON in a `<pre>` block.
        """
        return format_html(
            "<pre style='white-space:pre-wrap;word-break:break-word;margin:0'>{}</pre>",
            obj.to_debug_json(),
        )

    @admin.display(description="Previous in series")
    def previous_in_series_link(self, obj: "SiteReport") -> str:
        """
        Link to the previous report in this series, if any.

        Args:
            obj (SiteReport): Site report instance.

        Returns:
            str: HTML anchor tag for the previous report or a dash when
            none exists.
        """
        prev_obj = obj.previous_in_series()
        if not prev_obj:
            return "—"
        url = reverse(
            f"admin:{prev_obj._meta.app_label}_{prev_obj._meta.model_name}_change",
            args=[prev_obj.pk],
        )
        label = f"{prev_obj.created_on:%Y-%m-%d %H:%M:%S} (id {prev_obj.pk})"
        return format_html('<a href="{}">{}</a>', url, label)

    @admin.display(description="Next in series")
    def next_in_series_link(self, obj: "SiteReport") -> str:
        """
        Link to the next report in this series, if any.

        Args:
            obj (SiteReport): Site report instance.

        Returns:
            str: HTML anchor tag for the next report or a dash when
            none exists.
        """
        next_obj = obj.next_in_series()
        if not next_obj:
            return "—"
        url = reverse(
            f"admin:{next_obj._meta.app_label}_{next_obj._meta.model_name}_change",
            args=[next_obj.pk],
        )
        label = f"{next_obj.created_on:%Y-%m-%d %H:%M:%S} (id {next_obj.pk})"
        return format_html('<a href="{}">{}</a>', url, label)

    def export_to_csv(
        self,
        request: HttpRequest,
        queryset: QuerySet[SiteReport],
    ) -> HttpResponse:
        """
        Export selected site reports as a CSV file.

        Args:
            request (HttpRequest): Current admin request.
            queryset (QuerySet[SiteReport]): Site reports to export.

        Returns:
            HttpResponse: Response that streams a CSV download.
        """
        return export_to_csv_action(
            self, request, queryset, field_names=SiteReport.DEFAULT_EXPORT_FIELDNAMES
        )

    def export_to_excel(
        self,
        request: HttpRequest,
        queryset: QuerySet[SiteReport],
    ) -> HttpResponse:
        """
        Export selected site reports as an Excel file.

        Args:
            request (HttpRequest): Current admin request.
            queryset (QuerySet[SiteReport]): Site reports to export.

        Returns:
            HttpResponse: Response that streams an Excel download.
        """
        return export_to_excel_action(
            self, request, queryset, field_names=SiteReport.DEFAULT_EXPORT_FIELDNAMES
        )

    actions = (export_to_csv, export_to_excel)


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
    def completion(self, obj: CampaignRetirementProgress) -> str:
        """
        Compute a human readable completion percentage for display.

        Args:
            obj (CampaignRetirementProgress): Progress instance.

        Returns:
            str: Percentage text such as `"100%"`.
        """
        if obj.complete:
            return "100%"
        total = obj.project_total + obj.item_total + obj.asset_total
        removed = obj.projects_removed + obj.items_removed + obj.assets_removed
        return "{}%".format(round(removed / total * 100, 2))


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    form = CardAdminForm
    fields = ("title", "display_heading", "body_text", "image", "image_alt_text")
    list_display = ["title", "display_heading", "created_on", "updated_on"]
    list_filter = (CardCampaignListFilter, "updated_on")


class TutorialInline(admin.TabularInline):
    model = TutorialCard
    extra = 1
    raw_id_fields = ("card",)


@admin.register(CardFamily)
class CardFamilyAdmin(admin.ModelAdmin):
    inlines = (TutorialInline,)

    class Media:
        js = ("admin/custom-inline.js",)


@admin.register(Guide)
class GuideAdmin(admin.ModelAdmin):
    form = GuideAdminForm


@admin.register(NextTranscribableCampaignAsset)
class NextTranscribableCampaignAssetAdmin(admin.ModelAdmin):
    list_display = (
        "asset",
        "transcription_status",
        "campaign",
        "created_on",
    )
    list_filter = (
        NextAssetCampaignListFilter,
        "transcription_status",
    )
    search_fields = (
        "asset__title",
        "item__title",
        "project__title",
        "campaign__title",
    )
    readonly_fields = (
        "asset",
        "sequence",
        "item",
        "item_item_id",
        "project",
        "project_slug",
        "campaign",
        "created_on",
    )
    ordering = ("-created_on",)


@admin.register(NextReviewableCampaignAsset)
class NextReviewableCampaignAssetAdmin(admin.ModelAdmin):
    list_display = (
        "asset",
        "campaign",
        "created_on",
    )
    list_filter = (NextAssetCampaignListFilter,)
    search_fields = (
        "asset__title",
        "item__title",
        "project__title",
        "campaign__title",
        "transcriber_ids",
    )
    readonly_fields = (
        "asset",
        "item",
        "project",
        "campaign",
        "transcriber_ids",
        "created_on",
    )
    ordering = ("-created_on",)


@admin.register(NextTranscribableTopicAsset)
class NextTranscribableTopicAssetAdmin(admin.ModelAdmin):
    list_display = (
        "asset",
        "transcription_status",
        "topic",
        "created_on",
    )
    list_filter = (
        TopicListFilter,
        "transcription_status",
    )
    search_fields = (
        "asset__title",
        "item__title",
        "project__title",
        "topic__title",
    )
    readonly_fields = (
        "asset",
        "sequence",
        "item",
        "item_item_id",
        "project",
        "project_slug",
        "topic",
        "created_on",
    )
    ordering = ("-created_on",)


@admin.register(NextReviewableTopicAsset)
class NextReviewableTopicAssetAdmin(admin.ModelAdmin):
    list_display = (
        "asset",
        "topic",
        "created_on",
    )
    list_filter = (TopicListFilter,)
    search_fields = (
        "asset__title",
        "item__title",
        "project__title",
        "topic__title",
        "transcriber_ids",
    )
    readonly_fields = (
        "asset",
        "item",
        "project",
        "topic",
        "transcriber_ids",
        "created_on",
    )
    ordering = ("-created_on",)


@admin.register(KeyMetricsReport)
class KeyMetricsReportAdmin(admin.ModelAdmin):
    form = KeyMetricsReportAdminForm

    readonly_fields = (
        "created_on",
        "updated_on",
        "period_type",
        "period_start",
        "period_end",
        "fiscal_year",
        "fiscal_quarter",
        "month",
        "download_csv_link",
    )

    list_display = (
        "period_type",
        "fiscal_year",
        "fiscal_quarter",
        "month",
        "period_start",
        "period_end",
        "updated_on",
    )
    list_filter = (
        "period_type",
        "fiscal_year",
        "fiscal_quarter",
        "month",
    )
    search_fields = ("period_type",)
    ordering = ("-period_start", "-period_end", "period_type")

    fieldsets = (
        (
            "Report details",
            {
                "description": (
                    "These fields describe which period this report covers and "
                    "when it was last updated. They cannot be edited here."
                ),
                "fields": (
                    "period_type",
                    "period_start",
                    "period_end",
                    "fiscal_year",
                    "fiscal_quarter",
                    "month",
                    "created_on",
                    "updated_on",
                    "download_csv_link",
                ),
            },
        ),
        (
            "Manual Fields (editable)",
            {
                "description": (
                    "You can type values here if you track them outside of "
                    "Concordia. Blank values are not included in quarterly or "
                    "fiscal-year totals. If you later add values for the "
                    "underlying months, those totals may update the quarterly "
                    "and fiscal-year reports when reports are rebuilt."
                ),
                "fields": (
                    "crowd_emails_and_libanswers_sent",
                    "crowd_visits",
                    "crowd_page_views",
                    "crowd_unique_visitors",
                    "avg_visit_seconds",
                    "transcriptions_added_to_loc_gov",
                    "datasets_added_to_loc_gov",
                ),
            },
        ),
        (
            "Calculated metrics (editable, may be overwritten)",
            {
                "description": (
                    "These numbers are usually calculated from Site Reports. "
                    "You can edit them here if needed, but they may be "
                    "overwritten when reports are rebuilt. Monthly reports can "
                    "be recomputed when new daily Site Reports arrive. "
                    "Quarterly reports can be recomputed when any monthly "
                    "report in the quarter is updated. Fiscal-year reports can "
                    "be recomputed when any quarterly report in the year is "
                    "updated."
                ),
                "fields": (
                    "assets_published",
                    "assets_started",
                    "assets_completed",
                    "users_activated",
                    "anonymous_transcriptions",
                    "transcriptions_saved",
                    "tag_uses",
                ),
            },
        ),
    )

    @admin.display(description="Download CSV")
    def download_csv_link(self, obj: "KeyMetricsReport") -> str:
        """
        Provide a link to download this report as a CSV file.

        Args:
            obj (KeyMetricsReport): Report instance.

        Returns:
            str: HTML anchor tag for the CSV download.
        """
        url = reverse(
            f"admin:{obj._meta.app_label}_{obj._meta.model_name}_download_csv",
            args=[obj.pk],
        )
        return format_html('<a class="button" href="{}">Download CSV</a>', url)

    def get_urls(self):
        """
        Register a custom admin view to serve CSV files for reports.

        Returns:
            list: Custom URL patterns combined with the default admin URLs.
        """
        urls = super().get_urls()
        opts = self.model._meta
        custom_urls = [
            path(
                "<path:object_id>/download_csv/",
                self.admin_site.admin_view(self.download_csv_view),
                name=f"{opts.app_label}_{opts.model_name}_download_csv",
            ),
        ]
        return custom_urls + urls

    def download_csv_view(
        self,
        request: HttpRequest,
        object_id: str,
    ) -> HttpResponse:
        """
        Serve the CSV for a single KeyMetricsReport instance.

        Args:
            request (HttpRequest): Current admin request.
            object_id (str): Primary key of the report to download.

        Returns:
            HttpResponse: CSV download response.

        Raises:
            Http404: If the report cannot be found.
        """
        obj = self.get_object(request, object_id)
        if obj is None:
            raise Http404("Report not found.")
        csv_bytes = obj.render_csv()
        response = HttpResponse(csv_bytes, content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{obj.csv_filename()}"'
        return response

    @admin.action(description="Download CSVs of selected reports as a ZIP")
    def download_selected_as_zip(
        self,
        request: HttpRequest,
        queryset: QuerySet[KeyMetricsReport],
    ) -> HttpResponse:
        """
        Stream a ZIP file containing one CSV per selected report.

        Args:
            request (HttpRequest): Current admin request.
            queryset (QuerySet[KeyMetricsReport]): Reports to export.

        Returns:
            HttpResponse: ZIP download response.
        """
        memory_file = io.BytesIO()
        with zipfile.ZipFile(
            memory_file, mode="w", compression=zipfile.ZIP_DEFLATED
        ) as zf:
            for report in queryset.order_by("period_start", "period_type"):
                zf.writestr(report.csv_filename(), report.render_csv())
        memory_file.seek(0)

        response = HttpResponse(memory_file.getvalue(), content_type="application/zip")
        response["Content-Disposition"] = (
            'attachment; filename="key_metrics_reports.zip"'
        )
        return response

    actions = ("download_selected_as_zip",)
