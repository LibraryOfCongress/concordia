import re
from datetime import date, datetime

from bittersweet.models import validated_get_or_create
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.template.defaultfilters import slugify
from django.views.decorators.cache import never_cache
from tabular_export.core import export_to_csv_response

from importer.tasks import import_items_into_project_from_url
from importer.utils.excel import slurp_excel

from ..forms import AdminProjectBulkImportForm
from ..models import (
    Asset,
    Campaign,
    Item,
    Project,
    SiteReport,
    Tag,
    Transcription,
    TranscriptionStatus,
    UserAssetTagCollection,
)


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
                    campaign, created = validated_get_or_create(
                        Campaign,
                        title=campaign_title,
                        defaults={
                            "slug": slugify(campaign_title),
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
                    project, created = validated_get_or_create(
                        Project,
                        title=project_title,
                        campaign=campaign,
                        defaults={
                            "slug": slugify(project_title),
                            "description": row["Project Description"] or "",
                            "campaign": campaign,
                        },
                    )
                except ValidationError as exc:
                    messages.error(
                        request,
                        request,
                        f"Unable to create project {project_title}: {exc}",
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

    assets_total = Asset.objects.count()
    assets_published = Asset.objects.filter(published=True).count()
    assets_not_started = Asset.objects.filter(
        transcription_status=TranscriptionStatus.NOT_STARTED
    ).count()
    assets_in_progress = Asset.objects.filter(
        transcription_status=TranscriptionStatus.IN_PROGRESS
    ).count()
    assets_waiting_review = Asset.objects.filter(
        transcription_status=TranscriptionStatus.SUBMITTED
    ).count()
    assets_completed = Asset.objects.filter(
        transcription_status=TranscriptionStatus.COMPLETED
    ).count()
    assets_unpublished = Asset.objects.filter(published=False).count()

    items_published = Item.objects.filter(published=True).count()
    items_unpublished = Item.objects.filter(published=False).count()

    projects_published = Project.objects.filter(published=True).count()
    projects_unpublished = Project.objects.filter(published=False).count()

    campaigns_published = Campaign.objects.filter(published=True).count()
    campaigns_unpublished = Campaign.objects.filter(published=False).count()

    users_registered = User.objects.all().count()
    users_activated = User.objects.filter(is_active=True).count()

    anonymous_transcriptions = Transcription.objects.filter(
        user__username="anonymous"
    ).count()
    transcriptions_saved = Transcription.objects.all().count()

    tag_collections = UserAssetTagCollection.objects.all()
    tag_count = 0
    distinct_tag_count = Tag.objects.all().count()

    for tag_group in tag_collections:
        tag_count += tag_group.tags.count()

    headers = [
        "Date",
        "Time",
        "Campaign",
        "Assets total",
        "Assets published",
        "Assets not started",
        "Assets in progress",
        "Assets waiting review",
        "Assets complete",
        "Assets unpublished",
        "Items published",
        "Items unpublished",
        "Projects published",
        "Projects unpublished",
        "Anonymous transcriptions",
        "Transcriptions saved",
        "Distinct Tags",
        "Tag Uses",
        "Campaigns published",
        "Campaigns unpublished",
        "Users registered",
        "Users activated",
    ]

    data = [
        [
            date.today(),
            datetime.time(datetime.now()),
            "All",
            assets_total,
            assets_published,
            assets_not_started,
            assets_in_progress,
            assets_waiting_review,
            assets_completed,
            assets_unpublished,
            items_published,
            items_unpublished,
            projects_published,
            projects_unpublished,
            anonymous_transcriptions,
            transcriptions_saved,
            distinct_tag_count,
            tag_count,
            campaigns_published,
            campaigns_unpublished,
            users_registered,
            users_activated,
        ]
    ]

    site_report = SiteReport()
    site_report.assets_total = assets_total
    site_report.assets_published = assets_published
    site_report.assets_not_started = assets_not_started
    site_report.assets_in_progress = assets_in_progress
    site_report.assets_waiting_review = assets_waiting_review
    site_report.assets_completed = assets_completed
    site_report.assets_unpublished = assets_unpublished
    site_report.items_published = items_published
    site_report.items_unpublished = items_unpublished
    site_report.projects_published = projects_published
    site_report.projects_unpublished = projects_unpublished
    site_report.anonymous_transcriptions = anonymous_transcriptions
    site_report.transcriptions_saved = transcriptions_saved
    site_report.distinct_tags = distinct_tag_count
    site_report.tag_uses = tag_count
    site_report.campaigns_published = campaigns_published
    site_report.campaigns_unpublished = campaigns_unpublished
    site_report.users_registered = users_registered
    site_report.users_activated = users_activated
    site_report.save()

    for campaign in Campaign.objects.all():
        data.append(get_campaign_report(campaign))

    return export_to_csv_response("site-report.csv", headers, data)


def get_campaign_report(campaign):

    assets_total = Asset.objects.filter(item__project__campaign__id=campaign.id).count()
    assets_published = Asset.objects.filter(
        item__project__campaign__id=campaign.id, published=True
    ).count()
    assets_not_started = Asset.objects.filter(
        item__project__campaign__id=campaign.id,
        transcription_status=TranscriptionStatus.NOT_STARTED,
    ).count()
    assets_in_progress = Asset.objects.filter(
        item__project__campaign__id=campaign.id,
        transcription_status=TranscriptionStatus.IN_PROGRESS,
    ).count()
    assets_waiting_review = Asset.objects.filter(
        item__project__campaign__id=campaign.id,
        transcription_status=TranscriptionStatus.SUBMITTED,
    ).count()
    assets_completed = Asset.objects.filter(
        item__project__campaign__id=campaign.id,
        transcription_status=TranscriptionStatus.COMPLETED,
    ).count()
    assets_unpublished = Asset.objects.filter(
        item__project__campaign__id=campaign.id, published=False
    ).count()

    items_published = Item.objects.filter(
        project__campaign__id=campaign.id, published=True
    ).count()
    items_unpublished = Item.objects.filter(
        project__campaign__id=campaign.id, published=False
    ).count()

    projects_published = Project.objects.filter(
        campaign__id=campaign.id, published=True
    ).count()
    projects_unpublished = Project.objects.filter(
        campaign__id=campaign.id, published=False
    ).count()

    anonymous_transcriptions = Transcription.objects.filter(
        asset__item__project__campaign__id=campaign.id, user__username="anonymous"
    ).count()
    transcriptions_saved = Transcription.objects.filter(
        asset__item__project__campaign__id=campaign.id
    ).count()

    asset_tag_collections = UserAssetTagCollection.objects.filter(
        asset__item__project__campaign__id=campaign.id
    )
    tag_count = 0
    distinct_tag_count = 0

    for tag_collection in asset_tag_collections:
        tag_count += tag_collection.tags.all().count()

    site_report = SiteReport()
    site_report.campaign = campaign
    site_report.assets_total = assets_total
    site_report.assets_published = assets_published
    site_report.assets_not_started = assets_not_started
    site_report.assets_in_progress = assets_in_progress
    site_report.assets_waiting_review = assets_waiting_review
    site_report.assets_completed = assets_completed
    site_report.assets_unpublished = assets_unpublished
    site_report.items_published = items_published
    site_report.items_unpublished = items_unpublished
    site_report.projects_published = projects_published
    site_report.projects_unpublished = projects_unpublished
    site_report.anonymous_transcriptions = anonymous_transcriptions
    site_report.transcriptions_saved = transcriptions_saved
    site_report.distinct_tags = distinct_tag_count
    site_report.tag_uses = tag_count
    site_report.save()

    return [
        date.today(),
        datetime.time(datetime.now()),
        campaign.title,
        assets_total,
        assets_published,
        assets_not_started,
        assets_in_progress,
        assets_waiting_review,
        assets_completed,
        assets_unpublished,
        items_published,
        items_unpublished,
        projects_published,
        projects_unpublished,
        anonymous_transcriptions,
        transcriptions_saved,
        distinct_tag_count,
        tag_count,
    ]
