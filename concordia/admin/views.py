import re
import tempfile
import time

from bittersweet.models import validated_get_or_create
from celery import Celery
from django.apps import apps
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import ValidationError
from django.db.models import OuterRef, Subquery
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.text import slugify
from django.views import View
from django.views.decorators.cache import never_cache
from tabular_export.core import export_to_csv_response, flatten_queryset

from concordia.models import Asset, Item, Transcription, TranscriptionStatus
from exporter.views import do_bagit_export
from importer.models import ImportItem, ImportItemAsset, ImportJob
from importer.tasks import (
    fetch_all_urls,
    import_items_into_project_from_url,
    redownload_image_task,
)
from importer.utils.excel import slurp_excel

from ..models import Campaign, Project, SiteReport
from .forms import AdminProjectBulkImportForm, AdminRedownloadImagesForm


@never_cache
@staff_member_required
@permission_required("concordia.add_item")
@permission_required("concordia.change_item")
def redownload_images_view(request):
    request.current_app = "admin"

    context = {"title": "Redownload Images"}

    if request.method == "POST":
        form = AdminRedownloadImagesForm(request.POST, request.FILES)

        if form.is_valid():
            context["assets_to_download"] = assets_to_download = []

            rows = slurp_excel(request.FILES["spreadsheet_file"])
            required_fields = [
                "download_url",
            ]
            for idx, row in enumerate(rows):
                missing_fields = [i for i in required_fields if i not in row]
                if missing_fields:
                    messages.warning(
                        request, f"Skipping row {idx}: missing fields {missing_fields}"
                    )
                    continue

                download_url = row["download_url"]
                # optional real_file_url data
                real_file_url = row["real_file_url"]

                if not download_url:
                    if not any(row.values()):
                        # No messages for completely blank rows
                        continue

                    warning_message = (
                        f"Skipping row {idx}: the required field "
                        "download_url is empty"
                    )
                    messages.warning(request, warning_message)
                    continue

                if not download_url.startswith("http"):
                    messages.warning(
                        request, f"Skipping unrecognized URL value: {download_url}"
                    )
                    continue

                try:
                    # Use the download_url to look up the related asset.
                    # Then queue the task to redownload the image file.
                    assets = Asset.objects.filter(download_url=download_url)
                    for asset in assets:
                        redownload_image_task.delay(asset.pk)

                        if real_file_url:
                            correct_assets = Asset.objects.filter(
                                download_url=real_file_url
                            )
                            for correct_asset in correct_assets:
                                asset.correct_asset_pk = correct_asset.pk
                                asset.correct_asset_slug = correct_asset.slug

                        assets_to_download.append(asset)

                    if not assets:
                        messages.warning(
                            request,
                            f"No matching asset for download URL {download_url}",
                        )

                    else:
                        messages.info(
                            request,
                            f"Queued download for {download_url}",
                        )
                except Exception as exc:
                    messages.error(
                        request,
                        f"Unhandled error attempting to import {download_url}: {exc}",
                    )
    else:
        form = AdminRedownloadImagesForm()

    context["form"] = form

    return render(request, "admin/redownload_images.html", context)


@never_cache
@staff_member_required
@permission_required("concordia.add_campaign")
@permission_required("concordia.change_campaign")
@permission_required("concordia.add_project")
@permission_required("concordia.change_project")
@permission_required("concordia.add_item")
@permission_required("concordia.change_item")
def project_level_export(request):
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
            return do_bagit_export(assets, export_base_dir, export_filename_base)

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
        for campaigns in Campaign.objects.all():
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
def celery_task_review(request):
    request.current_app = "admin"
    totalcount = 0
    counter = 0
    asset_successful = 0
    asset_incomplete = 0
    asset_unstarted = 0
    asset_failure = 0
    context = {
        "title": "Active Importer Tasks",
        "campaigns": [],
        "projects": [],
    }
    celery = Celery("concordia")
    celery.config_from_object("django.conf:settings", namespace="CELERY")
    idx = request.GET.get("id")

    if idx is not None:
        form = AdminProjectBulkImportForm()
        projects = Project.objects.filter(campaign_id=int(idx))
        for project in projects:
            asset_successful = 0
            asset_failure = 0
            asset_incomplete = 0
            asset_unstarted = 0
            proj_dict = {}
            proj_dict["title"] = project.title
            proj_dict["id"] = project.pk
            proj_dict["campaign_id"] = idx
            messages.info(request, f"{project.title}")
            importjobs = ImportJob.objects.filter(project_id=project.pk).order_by(
                "-created"
            )
            for importjob in importjobs:
                job_id = importjob.pk
                assets = ImportItem.objects.filter(job_id=job_id).order_by("-created")
                for asset in assets:
                    counter = counter + 1
                    assettasks = ImportItemAsset.objects.filter(import_item_id=asset.pk)
                    countasset = 0
                    for assettask in assettasks:
                        if (
                            assettask.failed is not None
                            and assettask.last_started is not None
                        ):
                            asset_failure = asset_failure + 1
                            messages.warning(
                                request,
                                f"{assettask.url}-{assettask.status}",
                            )
                        elif (
                            assettask.completed is None
                            and assettask.last_started is not None
                        ):
                            asset_incomplete = asset_incomplete + 1
                            messages.warning(
                                request,
                                f"{assettask.url}-{assettask.status}",
                            )
                        elif (
                            assettask.completed is None
                            and assettask.last_started is None
                        ):
                            asset_unstarted = asset_unstarted + 1
                            messages.warning(
                                request,
                                f"{assettask.url}-{assettask.status}",
                            )
                        else:
                            asset_successful = asset_successful + 1
                            messages.info(
                                request,
                                f"{assettask.url}-{assettask.status}",
                            )
                        countasset = countasset + 1
                        totalcount = totalcount + 1
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
        form = AdminProjectBulkImportForm()

    context["form"] = form
    return render(request, "admin/celery_task.html", context)


@never_cache
@staff_member_required
@permission_required("concordia.add_campaign")
@permission_required("concordia.change_campaign")
@permission_required("concordia.add_project")
@permission_required("concordia.change_project")
@permission_required("concordia.add_item")
@permission_required("concordia.change_item")
def admin_bulk_import_review(request):
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
                    if campaign_slug and not pattern.match(campaign_slug):
                        messages.warning(
                            request, "Campaign slug doesn't match pattern."
                        )

                        # Read Project slug value from excel
                    project_slug = row["Project Slug"]
                    if project_slug and not pattern.match(project_slug):
                        messages.warning(request, "Project slug doesn't match pattern.")

                    potential_urls = filter(None, re.split(r"[\s]+", import_url_blob))

                    for url in potential_urls:
                        if not url.startswith("http"):
                            messages.warning(
                                request, f"Skipping unrecognized URL value: {url}"
                            )
                            continue

                        try:
                            urls.append(url)
                            url_counter = url_counter + 1

                            if url_counter == 50:
                                all_urls.append(urls)
                                url_counter = 0
                                urls = []

                        except Exception as exc:
                            messages.error(
                                request,
                                f"Unhandled error attempting to count {url}: {exc}",
                            )

                all_urls.append(urls)
                for _i, val in enumerate(all_urls):
                    return_result = fetch_all_urls(val)
                    for res in return_result[0]:
                        messages.info(request, f"{res}")

                    sum_count = sum_count + return_result[1]
                    time.sleep(7)

                messages.info(request, f"Total Asset Count:{sum_count}")
            finally:
                messages.info(request, "All Processes Completed")

    else:
        form = AdminProjectBulkImportForm()

    context["form"] = form

    return render(request, "admin/bulk_review.html", context)


@never_cache
@staff_member_required
@permission_required("concordia.add_campaign")
@permission_required("concordia.change_campaign")
@permission_required("concordia.add_project")
@permission_required("concordia.change_project")
@permission_required("concordia.add_item")
@permission_required("concordia.change_item")
def admin_bulk_import_view(request):
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
                    if campaign_slug and not pattern.match(campaign_slug):
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
                    if project_slug and not pattern.match(project_slug):
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
                        request, f"Reusing project {project_title} without modification"
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
                            f"Queued {campaign_title} {project_title} import for {url}",
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
def admin_site_report_view(request):
    site_reports = SiteReport.objects.all()

    headers, data = flatten_queryset(
        site_reports,
        field_names=SiteReport.DEFAULT_EXPORT_FIELDNAMES,
        extra_verbose_names={"created_on": "Date", "campaign__title": "Campaign"},
    )

    return export_to_csv_response("site-report.csv", headers, data)


@never_cache
@staff_member_required
def admin_retired_site_report_view(request):
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
    def get(self, request, *args, **kwargs):
        model_name = request.GET.get("model_name")
        object_id = request.GET.get("object_id")
        field_name = request.GET.get("field_name")

        model = apps.get_model(app_label="concordia", model_name=model_name)
        instance = model.objects.get(pk=object_id)
        value = getattr(instance, field_name)

        return JsonResponse({field_name: value})
