import os
import re
import time
import shutil
import tempfile
import requests
import json
from urllib.parse import parse_qs, urlparse
from django.views.generic import FormView
from django.core.files.uploadhandler import TemporaryFileUploadHandler
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from bittersweet.models import validated_get_or_create
from celery import Celery
from celery.result import AsyncResult
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.utils.text import slugify
from django.views.decorators.cache import never_cache
from tabular_export.core import export_to_csv_response, flatten_queryset
from django.http import HttpResponse, HttpResponseRedirect
from importer.models import ImportItem, ImportItemAsset, ImportJob
from importer.tasks import (
    fetch_all_urls,
    import_items_into_project_from_url,
    redownload_image_task,
)
from importer.utils.excel import slurp_excel
from concordia.models import Asset, Item, Transcription, TranscriptionStatus
from django.db.models import OuterRef, Subquery
from exporter.views import do_bagit_export
from ..models import Asset, Campaign, Project, SiteReport
from .forms import (
    AdminProjectBulkImportForm,
    AdminRedownloadImagesForm,
    AdminProcessBagitForm,
)

# Get the JSON for any loc.gov URL
# Will retry until it has valid JSON
# Returns the JSON, or 404 if status == 404
def get_locgov_json(url, locgov_server):
    loc_json = None
    while loc_json == None:
        r = requests.get(url)
        try:
            loc_json = json.loads(r.text)
        except:
            time.sleep(5)
            pass
    if "status" in loc_json and loc_json["status"] == 404:
        return 404
    return loc_json


# Return the Item JSON for a loc.gov /item
def locgov_item(item, locgov_server):
    url_start = "https://%s.loc.gov/item/" % locgov_server
    url = url_start + item + "/?fo=json&at=item"
    item_json = get_locgov_json(url)
    if item_json == 404:
        return 404
    return item_json["item"]


# Returns the Resources given an Item URL
# This should have file data for all files in all of the item's resources
def locgov_item_resources(item, locgov_server):
    url_start = "https://%s.loc.gov/item/" % locgov_server
    url = url_start + item + "/?fo=json&at=resources"
    resources_json = get_locgov_json(url, "www")
    if resources_json == 404:
        return 404
    return resources_json["resources"]


# Get the Item for a given Resource
def locgov_resource_item_section(resource, locgov_server):
    if not resource.endswith("/"):
        resource = resource + "/"
    url = resource + "?fo=json&at=item"
    item_json = get_locgov_json(url, locgov_server)

    if item_json == 404:
        return 404
    return item_json["item"]


# Script to generate concatinated transcription files, and make resource dirs for receive to CTS
# Run script in data directory
# at same level as item-resource-urls.txt


def locgov_create_resources(resource_dir):

    # cwd = os.getcwd()
    cwd = resource_dir
    item_file = os.path.join(cwd, "item-resource-urls.txt")

    # resource for txt looks like = 'http://www.loc.gov/resource/mss85943.002514/'

    # Resource TXT file has repeated rows - get all unique Resource URLS
    resource_urls = []
    with open(item_file, "r", encoding="utf-8") as item_txt:
        for line in item_txt:
            r = line.strip()
            if r not in resource_urls:
                resource_urls.append(r)

    for resource in resource_urls:
        resource_id = resource.split("/")[-2]

        # Filename of concat file will be last section of Resource URL, after the period
        concat_filename = resource.rsplit(".", 1)[-1].replace("/", "") + ".txt"

        # Get the item for the resource - stored in item['id']
        item = locgov_resource_item_section(resource, "www")
        # item_id = item['id']  #when ['item']['id'] is a item id (not a loc.gov/item url)
        item_id = item["id"].split("/")[
            -2
        ]  # when ['item']['id'] is a loc.gov/item url (not item id)

        # Get the resources for that item, and find the resource that is this resource
        # (May be multiple resources per item)
        # Get the files list for that resource
        resources = locgov_item_resources(item_id, "www")
        for r in resources:
            if resource_id in r["url"]:
                files = r["files"]

        # Get the expected list of text files matching each TIFF from the files list
        # Text file should be located at filepath matching TIFF after /master
        txt_files = []
        for f in files:
            for s in f:
                if s["mimetype"] == "image/tiff":
                    txt_files.append(
                        s["url"].rsplit("/master", 1)[-1].replace(".tif", ".txt")
                    )
        # Path to new concat_file - filepath of first text file, minus the filename of that file,
        #  adding on concat_filename
        concat_file = cwd + txt_files[0].rsplit("/", 1)[0] + "/" + concat_filename
        # Open/create the concat file, append each txt file, if it exists
        # (Some txt files may not exist because there was no content to transcribe)
        # Each line from txt appended, unless it contains 'crowd.loc.gov'
        with open(concat_file, "w", encoding="utf-8") as concat_write:
            attribution = ""
            for t in txt_files:
                trans_file = cwd + t
                if os.path.isfile(trans_file):
                    with open(trans_file, "r", encoding="utf-8") as trans_file:
                        for l in trans_file:
                            if "crowd.loc.gov" in l:
                                attribution = l
                                continue
                            else:
                                concat_write.write(l)
            concat_write.write(attribution)

        # Make resource dir if it does not exist - named by resource id, swapping . for -
        # copy in concat file
        resource_dir = cwd + "/" + resource_id.replace(".", "-")
        if not os.path.isdir(resource_dir):
            os.mkdir(resource_dir)
        new_concat_file = resource_dir + "/" + concat_filename
        copy = concat_file + " -> " + new_concat_file
        shutil.copyfile(concat_file, new_concat_file)

        # copy all of the resource's txt files into the new resource dir
        for t in txt_files:
            trans_file = cwd + t
            trans_filename = t.rsplit("/", 1)[-1]
            new_trans_file = resource_dir + "/" + trans_filename
            if os.path.isfile(trans_file):
                copy = trans_file + " -> " + new_trans_file
                shutil.copyfile(trans_file, new_trans_file)


def unzip_export(export_base_dir, export_filename_base, zip_file_name):
    # Download zip from local storage
    export_filename = "%s.zip" % export_filename_base
    with open("%s.zip" % export_base_dir, "rb") as zip_file:
        response = HttpResponse(zip_file, content_type="application/zip")
    response["Content-Disposition"] = "attachment; filename=%s" % zip_file_name
    return response


@csrf_exempt
def process_bagit_view(request):
    request.upload_handlers = [TemporaryFileUploadHandler(request=request)]
    return _process_bagit_view(request)


@csrf_protect
@never_cache
@staff_member_required
@permission_required("concordia.add_item")
@permission_required("concordia.change_item")
def _process_bagit_view(request):
    request.current_app = "admin"
    context = {"title": "Bagit Structure Processing"}

    if request.method == "POST":
        form = AdminProcessBagitForm(request.POST, request.FILES)
        zip_file_name = request.FILES["zip_file"].name
        export_filename_base = "%s" % (zip_file_name)

        with tempfile.TemporaryDirectory(
            prefix=export_filename_base
        ) as export_base_dir:
            messages.info(request, "test")
            archive_format = "zip"
            filepath = request.FILES["zip_file"].file.name
            shutil.unpack_archive(filepath, export_base_dir, archive_format)
            archive_name = export_base_dir
            export_dir = export_base_dir + "/data"
            locgov_create_resources(export_dir)
            shutil.make_archive(archive_name, "zip", export_base_dir)
            return unzip_export(export_base_dir, archive_name, zip_file_name)

    else:
        form = AdminProcessBagitForm()

    context["form"] = form

    return render(request, "admin/process_bagit.html", context)


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
    context = {"title": "Project Level Exporter"}
    form = AdminProjectBulkImportForm()
    context["campaigns"] = all_campaigns = []
    context["projects"] = all_projects = []
    id = request.GET.get("id")

    if request.method == "POST":

        project_list = request.POST.getlist("project_name")
        campaign_slug = request.GET.get("slug")

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

        export_filename_base = "%s" % (campaign_slug,)

        with tempfile.TemporaryDirectory(
            prefix=export_filename_base
        ) as export_base_dir:
            return do_bagit_export(assets, export_base_dir, export_filename_base)

    if id is not None:
        context["campaigns"] = []
        form = AdminProjectBulkImportForm()
        projects = Project.objects.filter(campaign_id=int(id))
        for project in projects:

            proj_dict = {}
            proj_dict["title"] = project.title
            proj_dict["id"] = project.pk
            proj_dict["campaign_id"] = id
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
    asset_succesful = 0
    asset_incomplete = 0
    asset_unstarted = 0
    asset_failure = 0
    context = {"title": "Active Importer Tasks"}
    celery = Celery("concordia")
    celery.config_from_object("django.conf:settings", namespace="CELERY")
    context["campaigns"] = all_campaigns = []
    context["projects"] = all_projects = []
    id = request.GET.get("id")

    if id is not None:
        context["campaigns"] = []
        form = AdminProjectBulkImportForm()
        projects = Project.objects.filter(campaign_id=int(id))
        for project in projects:
            asset_succesful = 0
            asset_failure = 0
            asset_incomplete = 0
            asset_unstarted = 0
            proj_dict = {}
            proj_dict["title"] = project.title
            proj_dict["id"] = project.pk
            proj_dict["campaign_id"] = id
            messages.info(request, f"{project.title}")
            importjobs = ImportJob.objects.filter(project_id=project.pk).order_by(
                "-created"
            )
            for importjob in importjobs:
                job_id = importjob.pk
                assets = ImportItem.objects.filter(job_id=job_id).order_by("-created")
                for asset in assets:
                    res = AsyncResult(str(asset.task_id))
                    counter = counter + 1
                    assettasks = ImportItemAsset.objects.filter(import_item_id=asset.pk)
                    countasset = 0
                    for assettask in assettasks:
                        if assettask.failed != None and assettask.last_started != None:
                            asset_failure = asset_failure + 1
                            messages.warning(
                                request,
                                f"{assettask.url}-{assettask.status}",
                            )
                        elif (
                            assettask.completed == None
                            and assettask.last_started != None
                        ):
                            asset_incomplete = asset_incomplete + 1
                            messages.warning(
                                request,
                                f"{assettask.url}-{assettask.status}",
                            )
                        elif (
                            assettask.completed == None
                            and assettask.last_started == None
                        ):
                            asset_unstarted = asset_unstarted + 1
                            messages.warning(
                                request,
                                f"{assettask.url}-{assettask.status}",
                            )
                        else:
                            asset_succesful = asset_succesful + 1
                            messages.info(
                                request,
                                f"{assettask.url}-{assettask.status}",
                            )
                        countasset = countasset + 1
                        totalcount = totalcount + 1
            proj_dict["succesful"] = asset_succesful
            proj_dict["incomplete"] = asset_incomplete
            proj_dict["unstarted"] = asset_unstarted
            proj_dict["failure"] = asset_failure
            all_projects.append(proj_dict)
        messages.info(request, f"{totalcount} Total Assets Processed")
        context["totalassets"] = totalcount

    else:
        context["projects"] = []
        for campaigns in Campaign.objects.all():
            all_campaigns.append(campaigns)
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
                for i, val in enumerate(all_urls):
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
                                request.user, project, url
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
