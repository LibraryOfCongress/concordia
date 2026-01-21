import logging
import re
import tempfile
import time
from http import HTTPStatus
from typing import Any

from django.apps import apps
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required, user_passes_test
from django.contrib.auth.models import User
from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.db.models import OuterRef, Prefetch, Subquery
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.text import slugify
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.generic.edit import FormView

from concordia.models import (
    Asset,
    Item,
    Transcription,
    TranscriptionStatus,
    validated_get_or_create,
)
from exporter.tabular_export.core import export_to_csv_response, flatten_queryset
from exporter.views import do_bagit_export
from importer.models import ImportItem, ImportItemAsset, ImportJob
from importer.tasks import fetch_all_urls
from importer.tasks.items import import_items_into_project_from_url
from importer.utils import slurp_excel

from ..models import Campaign, Project, SiteReport
from .forms import (
    AdminAssetsBulkChangeStatusForm,
    AdminProjectBulkImportForm,
    ClearCacheForm,
)
from .utils import _bulk_change_status

logger = logging.getLogger(__name__)


@never_cache
@staff_member_required
@permission_required("concordia.add_campaign")
@permission_required("concordia.change_campaign")
@permission_required("concordia.add_project")
@permission_required("concordia.change_project")
@permission_required("concordia.add_item")
@permission_required("concordia.change_item")
def project_level_export(request: HttpRequest) -> HttpResponse:
    """
    Render the project-level BagIt export admin view and run exports.

    When called with `GET`, shows a form to select campaigns and projects.
    When called with `POST`, builds a BagIt export for completed items in
    the selected projects.

    Request Parameters:
        `id` (str, optional): Campaign primary key used to filter projects.
        `slug` (str, optional): Campaign slug used when building the export
            filename.

    Args:
        request (HttpRequest): Current admin request.

    Returns:
        HttpResponse: HTML response for the selection view or a streamed
            BagIt export.
    """
    request.current_app = "admin"
    context = {"title": "Project Level Bagit Exporter"}
    form = AdminProjectBulkImportForm()
    context["campaigns"] = all_campaigns = []
    context["projects"] = all_projects = []
    idx = request.GET.get("id")

    if request.method == "POST":
        project_list = request.POST.getlist("project_name")
        campaign_slug = request.GET.get("slug")

        proj_titles = "_projects"

        item_qs = Item.objects.filter(
            project__campaign__slug=campaign_slug, project__id__in=project_list
        )
        incomplete_item_assets = Asset.objects.filter(
            item__in=item_qs,
            transcription_status__in=(
                TranscriptionStatus.NOT_STARTED,
                TranscriptionStatus.IN_PROGRESS,
                TranscriptionStatus.SUBMITTED,
            ),
        )
        item_qs = item_qs.exclude(asset__in=incomplete_item_assets)
        asset_qs = Asset.objects.filter(item__in=item_qs).order_by(
            "item__project", "item", "sequence"
        )
        item_qs = asset_qs

        latest_trans_subquery = (
            Transcription.objects.filter(asset=OuterRef("pk"))
            .order_by("-pk")
            .values("text")
        )

        assets = asset_qs.annotate(
            latest_transcription=Subquery(latest_trans_subquery[:1])
        )

        campaign_slug_dbv = Campaign.objects.get(slug__exact=campaign_slug).slug

        export_filename_base = "%s%s" % (
            campaign_slug_dbv,
            proj_titles,
        )

        with tempfile.TemporaryDirectory(
            prefix=export_filename_base
        ) as export_base_dir:
            return do_bagit_export(
                assets, export_base_dir, export_filename_base, request
            )

    if idx is not None:
        context["campaigns"] = []
        form = AdminProjectBulkImportForm()
        projects = Project.objects.filter(campaign_id=int(idx))
        for project in projects:
            proj_dict = {}
            proj_dict["title"] = project.title
            proj_dict["id"] = project.pk
            proj_dict["campaign_id"] = idx
            all_projects.append(proj_dict)

    else:
        context["projects"] = []
        for campaigns in Campaign.objects.exclude(status=Campaign.Status.RETIRED):
            all_campaigns.append(campaigns)
        form = AdminProjectBulkImportForm()

    context["form"] = form
    return render(request, "admin/project_level_export.html", context)


@never_cache
@staff_member_required
@permission_required("concordia.add_campaign")
@permission_required("concordia.change_campaign")
@permission_required("concordia.add_project")
@permission_required("concordia.change_project")
@permission_required("concordia.add_item")
@permission_required("concordia.change_item")
def celery_task_review(request: HttpRequest) -> HttpResponse:
    """
    Inspect importer Celery tasks and summarize their status by project.

    For a selected campaign, iterates through related projects, import
    jobs and item assets to count successful, incomplete, unstarted and
    failed tasks. Writes per-asset status messages to the admin message
    framework and renders a summary table.

    Request Parameters:
        `id` (str, optional): Campaign primary key used to select which
            projects to inspect.

    Args:
        request (HttpRequest): Current admin request.

    Returns:
        HttpResponse: HTML response showing task counts by project or a
            campaign picker.
    """
    request.current_app = "admin"
    totalcount = 0
    counter = 0
    asset_successful = 0
    asset_incomplete = 0
    asset_unstarted = 0
    asset_failure = 0
    context = {
        "title": "Importer Tasks",
        "campaigns": [],
        "projects": [],
    }
    idx = request.GET.get("id")

    if idx is not None:
        for project in Project.objects.filter(campaign_id=int(idx)):
            asset_successful = 0
            asset_failure = 0
            asset_incomplete = 0
            asset_unstarted = 0
            proj_dict = {"title": project.title, "id": project.pk, "campaign_id": idx}
            messages.info(request, f"{project.title}")
            for importjob in ImportJob.objects.filter(project_id=project.pk).order_by(
                "-created"
            ):
                for asset in ImportItem.objects.filter(job_id=importjob.pk).order_by(
                    "-created"
                ):
                    counter += 1
                    countasset = 0
                    for assettask in ImportItemAsset.objects.filter(
                        import_item_id=asset.pk
                    ):
                        if (
                            assettask.failed is not None
                            and assettask.last_started is not None
                        ):
                            asset_failure += 1
                            messages.warning(
                                request,
                                f"{assettask.url}-{assettask.status}",
                            )
                        elif (
                            assettask.completed is None
                            and assettask.last_started is not None
                        ):
                            asset_incomplete += 1
                            messages.warning(
                                request,
                                f"{assettask.url}-{assettask.status}",
                            )
                        elif (
                            assettask.completed is None
                            and assettask.last_started is None
                        ):
                            asset_unstarted += 1
                            messages.warning(
                                request,
                                f"{assettask.url}-{assettask.status}",
                            )
                        else:
                            asset_successful += 1
                            messages.info(
                                request,
                                f"{assettask.url}-{assettask.status}",
                            )
                        countasset += 1
                        totalcount += 1
            proj_dict["successful"] = asset_successful
            proj_dict["incomplete"] = asset_incomplete
            proj_dict["unstarted"] = asset_unstarted
            proj_dict["failure"] = asset_failure
            context["projects"].append(proj_dict)
        messages.info(request, f"{totalcount} Total Assets Processed")
        context["totalassets"] = totalcount
    else:
        context["campaigns"] = Campaign.objects.exclude(
            status=Campaign.Status.RETIRED
        ).order_by("-launch_date")

    return render(request, "admin/celery_task.html", context)


@never_cache
@staff_member_required
@permission_required("concordia.add_campaign")
@permission_required("concordia.change_campaign")
@permission_required("concordia.add_project")
@permission_required("concordia.change_project")
@permission_required("concordia.add_item")
@permission_required("concordia.change_item")
def admin_bulk_import_review(request: HttpRequest) -> HttpResponse:
    """
    Preview a bulk import spreadsheet without creating campaigns or items.

    Parses the uploaded spreadsheet, validates required columns and slugs
    and extracts all import URLs. Uses `fetch_all_urls` to preflight the
    URLs then reports the results and total asset count in admin messages.

    Request Parameters:
        Uploaded file `spreadsheet_file` (multipart): Spreadsheet with one
            row per campaign and project definition.

    Args:
        request (HttpRequest): Current admin request.

    Returns:
        HttpResponse: HTML response containing the review form and any
            status messages.
    """
    request.current_app = "admin"
    url_regex = r"[-\w+]+"
    pattern = re.compile(url_regex)
    context = {"title": "Bulk Import Review"}

    urls = []
    all_urls = []
    url_counter = 0
    sum_count = 0
    if request.method == "POST":
        form = AdminProjectBulkImportForm(request.POST, request.FILES)

        if form.is_valid():
            rows = slurp_excel(request.FILES["spreadsheet_file"])
            required_fields = [
                "Campaign",
                "Campaign Short Description",
                "Campaign Long Description",
                "Campaign Slug",
                "Project Slug",
                "Project",
                "Project Description",
                "Import URLs",
            ]
            try:
                for idx, row in enumerate(rows):
                    missing_fields = [i for i in required_fields if i not in row]
                    if missing_fields:
                        messages.warning(
                            request,
                            f"Skipping row {idx}: missing fields {missing_fields}",
                        )
                        continue

                    campaign_title = row["Campaign"]
                    project_title = row["Project"]
                    import_url_blob = row["Import URLs"]

                    if not all((campaign_title, project_title, import_url_blob)):
                        if not any(row.values()):
                            # No messages for completely blank rows
                            continue

                        warning_message = (
                            f"Skipping row {idx}: at least one required field "
                            "(Campaign, Project, Import URLs) is empty"
                        )
                        messages.warning(request, warning_message)
                        continue

                    # Read Campaign slug value from excel
                    campaign_slug = row["Campaign Slug"]
                    if campaign_slug and not pattern.fullmatch(campaign_slug):
                        messages.warning(
                            request, "Campaign slug doesn't match pattern."
                        )

                    # Read Project slug value from excel
                    project_slug = row["Project Slug"]
                    if project_slug and not pattern.fullmatch(project_slug):
                        messages.warning(request, "Project slug doesn't match pattern.")

                    potential_urls = filter(None, re.split(r"[\s]+", import_url_blob))

                    for url in potential_urls:
                        if not url.startswith("http"):
                            messages.warning(
                                request, f"Skipping unrecognized URL value: {url}"
                            )
                            continue

                        urls.append(url)
                        url_counter = url_counter + 1

                        if url_counter == 50:
                            all_urls.append(urls)
                            url_counter = 0
                            urls = []

                all_urls.append(urls)
                for _i, val in enumerate(all_urls):
                    return_result = fetch_all_urls(val)
                    for res in return_result[0]:
                        messages.info(request, f"{res}")

                    sum_count = sum_count + return_result[1]
                    time.sleep(7)

                messages.info(request, f"Total Asset Count:{sum_count}")
            finally:
                messages.info(request, "All Processes Completed")

    else:
        form = AdminProjectBulkImportForm()

    context["form"] = form

    return render(request, "admin/bulk_review.html", context)


@method_decorator(staff_member_required, name="dispatch")
@method_decorator(never_cache, name="dispatch")
class AdminBulkChangeAssetStatusView(FormView):
    template_name = "admin/bulk_change.html"
    form_class = AdminAssetsBulkChangeStatusForm

    def form_valid(self, form):
        try:
            rows = slurp_excel(self.request.FILES["spreadsheet_file"])
        except Exception as e:
            messages.error(self.request, f"Could not read spreadsheet: {e}")

            return self.render_to_response(self.get_context_data(form=form))
        total_in_sheet = len(rows)

        # Normalize and validate statuses from spreadsheet rows
        def normalize_status(status):
            if status is not None:
                v = str(status).strip().lower()
                # accept canonical keys from TranscriptionStatus
                valid = {
                    TranscriptionStatus.NOT_STARTED,
                    TranscriptionStatus.IN_PROGRESS,
                    TranscriptionStatus.SUBMITTED,
                    TranscriptionStatus.COMPLETED,
                }
                if v in valid:
                    return v
            return None

        normalized_rows = []
        invalid_rows = 0
        slugs_all = set()

        user_ids = {row.get("user") for row in rows if row.get("user")}
        users = {u.id: u for u in User.objects.filter(id__in=user_ids)}

        for row in rows:
            slug = row.get("asset__slug")
            status_raw = row.get("New Status", TranscriptionStatus.SUBMITTED)
            user_id = row.get("user", None)
            status = normalize_status(status_raw)
            if slug and status_raw:
                slugs_all.add(slug)
                normalized_row = {
                    "slug": slug,
                    "status": status,
                }
                if user_id:
                    normalized_row["user"] = users.get(user_id)
                normalized_rows.append(normalized_row)
            else:
                invalid_rows += 1

        # Fetch matched assets once
        assets_qs = Asset.objects.filter(slug__in=slugs_all).prefetch_related(
            Prefetch(
                "transcription_set",
                queryset=Transcription.objects.order_by("-pk"),
                to_attr="prefetched_transcriptions",
            )
        )
        matched = assets_qs.count()

        if matched == 0:
            messages.warning(
                self.request,
                (
                    f"No matching assets found in database. "
                    f"Spreadsheet contained {total_in_sheet} rows."
                ),
            )
            return self.render_to_response(self.get_context_data(form=form))

        updated_total = _bulk_change_status(self.request.user, normalized_rows)

        unmatched = len(slugs_all) - matched

        messages.success(
            self.request,
            (
                f"Processed spreadsheet with {total_in_sheet} rows. "
                f"Updated {updated_total} assets. "
                f"{invalid_rows} invalid rows. "
                f"{unmatched} unmatched asset slugs. "
            ),
        )
        return self.render_to_response(self.get_context_data(form=form))


@never_cache
@staff_member_required
@permission_required("concordia.add_campaign")
@permission_required("concordia.change_campaign")
@permission_required("concordia.add_project")
@permission_required("concordia.change_project")
@permission_required("concordia.add_item")
@permission_required("concordia.change_item")
def admin_bulk_import_view(request: HttpRequest) -> HttpResponse:
    """
    Queue bulk import jobs from a spreadsheet.

    Reads an uploaded spreadsheet, creates or reuses `Campaign` and
    `Project` records using `validated_get_or_create` then queues import
    jobs via `import_items_into_project_from_url` for each URL.

    Request Parameters:
        Uploaded file `spreadsheet_file` (multipart): Spreadsheet defining
            campaigns, projects and URLs.
        Field `redownload` (bool, optional): If true, forces existing
            items to be re-downloaded.

    Args:
        request (HttpRequest): Current admin request.

    Returns:
        HttpResponse: HTML response containing the bulk import form and
            any queued job information.
    """
    request.current_app = "admin"
    url_regex = r"[-\w+]+"
    pattern = re.compile(url_regex)
    context = {"title": "Bulk Import"}

    if request.method == "POST":
        form = AdminProjectBulkImportForm(request.POST, request.FILES)

        if form.is_valid():
            context["import_jobs"] = import_jobs = []
            redownload = form.cleaned_data.get("redownload", False)

            rows = slurp_excel(request.FILES["spreadsheet_file"])
            required_fields = [
                "Campaign",
                "Campaign Short Description",
                "Campaign Long Description",
                "Campaign Slug",
                "Project Slug",
                "Project",
                "Project Description",
                "Import URLs",
            ]
            for idx, row in enumerate(rows):
                missing_fields = [i for i in required_fields if i not in row]
                if missing_fields:
                    messages.warning(
                        request, f"Skipping row {idx}: missing fields {missing_fields}"
                    )
                    continue

                campaign_title = row["Campaign"]
                project_title = row["Project"]
                import_url_blob = row["Import URLs"]

                if not all((campaign_title, project_title, import_url_blob)):
                    if not any(row.values()):
                        # No messages for completely blank rows
                        continue

                    warning_message = (
                        f"Skipping row {idx}: at least one required field "
                        "(Campaign, Project, Import URLs) is empty"
                    )
                    messages.warning(request, warning_message)
                    continue

                try:
                    # Read Campaign slug value from excel
                    campaign_slug = row["Campaign Slug"]
                    if campaign_slug and not pattern.fullmatch(campaign_slug):
                        messages.warning(
                            request, "Campaign slug doesn't match pattern."
                        )
                    campaign, created = validated_get_or_create(
                        Campaign,
                        title=campaign_title,
                        defaults={
                            "slug": row["Campaign Slug"]
                            or slugify(campaign_title, allow_unicode=True),
                            "description": row["Campaign Long Description"] or "",
                            "short_description": row["Campaign Short Description"]
                            or "",
                        },
                    )
                except ValidationError as exc:
                    messages.error(
                        request, f"Unable to create campaign {campaign_title}: {exc}"
                    )
                    continue

                if created:
                    messages.info(request, f"Created new campaign {campaign_title}")
                else:
                    messages.info(
                        request,
                        f"Reusing campaign {campaign_title} without modification",
                    )

                try:
                    # Read Project slug value from excel
                    project_slug = row["Project Slug"]
                    if project_slug and not pattern.fullmatch(project_slug):
                        messages.warning(request, "Project slug doesn't match pattern.")
                    project, created = validated_get_or_create(
                        Project,
                        title=project_title,
                        campaign=campaign,
                        defaults={
                            "slug": row["Project Slug"]
                            or slugify(project_title, allow_unicode=True),
                            "description": row["Project Description"] or "",
                            "campaign": campaign,
                        },
                    )
                except ValidationError as exc:
                    messages.error(
                        request, f"Unable to create project {project_title}: {exc}"
                    )
                    continue

                if created:
                    messages.info(request, f"Created new project {project_title}")
                else:
                    messages.info(
                        request,
                        f"Reusing project {project_title} without modification",
                    )

                potential_urls = filter(None, re.split(r"[\s]+", import_url_blob))
                for url in potential_urls:
                    if not url.startswith("http"):
                        messages.warning(
                            request, f"Skipping unrecognized URL value: {url}"
                        )
                        continue

                    try:
                        import_jobs.append(
                            import_items_into_project_from_url(
                                request.user, project, url, redownload
                            )
                        )

                        messages.info(
                            request,
                            (
                                f"Queued {campaign_title} {project_title} "
                                f"import for {url}"
                            ),
                        )
                    except Exception as exc:
                        messages.error(
                            request,
                            f"Unhandled error attempting to import {url}: {exc}",
                        )
    else:
        form = AdminProjectBulkImportForm()

    context["form"] = form

    return render(request, "admin/bulk_import.html", context)


@never_cache
@staff_member_required
def admin_site_report_view(request: HttpRequest) -> HttpResponse:
    """
    Export all `SiteReport` records as a CSV file.

    Builds tabular data using `flatten_queryset` and returns a CSV
    response suitable for download.

    Args:
        request (HttpRequest): Current admin request.

    Returns:
        HttpResponse: CSV download with one row per `SiteReport`.
    """
    site_reports = SiteReport.objects.all()

    headers, data = flatten_queryset(
        site_reports,
        field_names=SiteReport.DEFAULT_EXPORT_FIELDNAMES,
        extra_verbose_names={"created_on": "Date", "campaign__title": "Campaign"},
    )

    return export_to_csv_response("site-report.csv", headers, data)


@never_cache
@staff_member_required
def admin_retired_site_report_view(request: HttpRequest) -> HttpResponse:
    """
    Export a CSV of the latest `SiteReport` per retired campaign.

    Selects the most recent report per retired campaign then appends a
    final summary row that totals numeric fields across all rows.

    Args:
        request (HttpRequest): Current admin request.

    Returns:
        HttpResponse: CSV download including per-campaign rows and a
            `RETIRED TOTAL` row.
    """
    site_reports = site_reports = (
        SiteReport.objects.filter(campaign__status=Campaign.Status.RETIRED)
        .order_by("campaign_id", "-created_on")
        .distinct("campaign_id")
    )

    headers, data = flatten_queryset(
        site_reports,
        field_names=SiteReport.DEFAULT_EXPORT_FIELDNAMES,
        extra_verbose_names={"created_on": "Date", "campaign__title": "Campaign"},
    )
    data = list(data)
    row = ["", "RETIRED TOTAL", "", ""]
    # You can't use aggregate with distinct(*fields), so the sum for each
    # has to be done in Python
    for field in SiteReport.DEFAULT_EXPORT_FIELDNAMES[4:]:
        row.append(
            sum(
                [
                    getattr(site_report, field) if getattr(site_report, field) else 0
                    for site_report in site_reports
                ]
            )
        )
    data.append(row)

    return export_to_csv_response("retired-site-report.csv", headers, data)


class SerializedObjectView(View):
    """
    Return a single field from a Concordia model instance as JSON.

    The model, instance and field to fetch are provided through query
    string parameters. This is intended for lightweight admin tools that
    need to inspect or preview stored values.
    """

    def get(
        self,
        request: HttpRequest,
        *args: Any,
        **kwargs: Any,
    ) -> JsonResponse:
        """
        Handle `GET` requests and serialize the requested field.

        Request Parameters:
            `model_name` (str): Name of the `concordia` app model to query.
            `object_id` (str): Primary key of the model instance.
            `field_name` (str): Name of the attribute or field to return.

        Args:
            request (HttpRequest): Current HTTP request.
            *args (Any): Positional arguments passed by the URLconf.
            **kwargs (Any): Keyword arguments passed by the URLconf.

        Returns:
            JsonResponse: JSON object containing the field value or a 404
                status if the instance does not exist.
        """
        model_name = request.GET.get("model_name")
        object_id = request.GET.get("object_id")
        field_name = request.GET.get("field_name")

        model = apps.get_model(app_label="concordia", model_name=model_name)
        try:
            instance = model.objects.get(pk=object_id)
            value = getattr(instance, field_name)
            return JsonResponse({field_name: value})
        except model.DoesNotExist:
            return JsonResponse({"status": "false"}, status=HTTPStatus.NOT_FOUND)


@method_decorator(never_cache, name="dispatch")
@method_decorator(user_passes_test(lambda u: u.is_superuser), name="dispatch")
class ClearCacheView(FormView):
    """
    Admin view for clearing non-default Django caches.

    Uses `ClearCacheForm` to pick a cache alias then calls `clear()` on
    the selected cache. Only superusers can access this view.
    """

    form_class = ClearCacheForm
    template_name = "admin/clear_cache.html"
    success_url = reverse_lazy("admin:clear-cache")

    def form_valid(self, form: ClearCacheForm) -> HttpResponse:
        """
        Clear the selected cache and redirect back to the form.

        On success, adds a success message. On failure, logs an error
        message then continues with the normal `FormView` redirect.

        Args:
            form (ClearCacheForm): Validated form containing the selected
                cache alias.

        Returns:
            HttpResponse: Redirect to the configured `success_url` after
                processing.
        """
        try:
            cache_name = form.cleaned_data["cache_name"]
            caches[cache_name].clear()
            messages.success(self.request, f"Successfully cleared '{cache_name}' cache")
        except Exception as err:
            messages.error(
                self.request,
                (
                    f"Couldn't clear cache '{cache_name}', "
                    f"something went wrong. Received error: {err}"
                ),
            )
        return super().form_valid(form)
