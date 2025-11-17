import os
import re
import shutil
import tempfile
from collections.abc import Iterable
from logging import getLogger
from pathlib import Path
from typing import Any, List

import bagit
import boto3
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.postgres.aggregates.general import StringAgg
from django.db.models import OuterRef, Subquery
from django.db.models.query import QuerySet
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseRedirect,
)
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from concordia.models import (
    Asset,
    Campaign,
    Item,
    Project,
    Transcription,
    TranscriptionStatus,
)
from exporter.exceptions import UnacceptableCharacterError
from exporter.tabular_export.core import export_to_csv_response, flatten_queryset
from exporter.utils import validate_text_for_export

logger = getLogger(__name__)


def get_latest_transcription_data(
    asset_qs: QuerySet[Asset],
) -> QuerySet[Asset]:
    """
    Annotate each asset with its latest transcription text.

    The annotation is named ``latest_transcription`` and is derived from the
    most recent ``Transcription`` by primary key.

    Args:
        asset_qs:
            QuerySet[Asset] to annotate.

    Returns:
        QuerySet[Asset]: The input queryset annotated with
        ``latest_transcription``.
    """
    latest_trans_subquery = (
        Transcription.objects.filter(asset=OuterRef("pk"))
        .order_by("-pk")
        .values("text")
    )

    assets = asset_qs.annotate(latest_transcription=Subquery(latest_trans_subquery[:1]))
    return assets


def get_tag_values(asset_qs: QuerySet[Asset]) -> QuerySet[Asset]:
    """
    Annotate each asset with a semicolon-joined string of tag values.

    The annotation is named ``tag_values`` and aggregates related tag text from
    ``userassettagcollection__tags__value``.

    Args:
        asset_qs:
            QuerySet[Asset] to annotate.

    Returns:
        QuerySet[Asset]: The input queryset annotated with ``tag_values``.
    """
    assets = asset_qs.annotate(
        tag_values=StringAgg("userassettagcollection__tags__value", "; ")
    )
    return assets


def remove_incomplete_items(item_qs: QuerySet[Item]) -> QuerySet[Asset]:
    """
    Filter out items that are not fully completed and return their assets.

    An item is considered incomplete if any of its assets have a status of
    NOT_STARTED, IN_PROGRESS or SUBMITTED.

    Args:
        item_qs:
            QuerySet[Item] to check for completeness.

    Returns:
        QuerySet[Asset]: Assets belonging to completed items, ordered by
        project, item and sequence.
    """
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
    return asset_qs


def get_original_asset_id(download_url: str) -> str:
    """
    Derive a stable external asset identifier from a LOC download URL.

    For ``tile.loc.gov`` URLs a best-effort pattern is used to extract the
    identifier. Non-matching URLs are returned unchanged.

    Args:
        download_url:
            The asset's download URL.

    Returns:
        str: Identifier suitable for naming files inside the BagIt payload.

    Raises:
        ValueError: If the URL looks like ``tile.loc.gov`` but no ID is found.
    """
    download_url = download_url.replace("https", "http")
    if download_url.startswith("http://tile.loc.gov/"):
        pattern = (
            r"/service:([A-Za-z0-9:.\-\_]+)/"
            + r"|/master/([A-Za-z0-9/]+)([0-9.]+)"
            + r"|/public:[A-Za-z0-9]+:([A-Za-z0-9:.\-_]+?)/"
        )
        asset_id = re.search(pattern, download_url)
        if not asset_id:
            logger.error(
                "Could not find a matching asset ID in download URL %s",
                download_url,
            )
            raise ValueError(
                f"Could not find a matching asset ID in download URL {download_url}"
            )
        matching_asset_id = next((group for group in asset_id.groups() if group))
        logger.debug(
            "Found asset ID %s in download URL %s",
            matching_asset_id,
            download_url,
        )
        return matching_asset_id

    logger.warning(
        "Download URL does not start with tile.loc.gov: %s",
        download_url,
    )
    return download_url


def write_distinct_asset_resource_file(
    assets: Iterable[Any], export_base_dir: str | Path
) -> None:
    """
    Write a unique list of resource URLs for the provided assets.

    The file is named ``item-resource-urls.txt`` and written at the export
    root. Each line contains one distinct ``Asset.resource_url``.

    Args:
        assets:
            Iterable of asset identifiers or a QuerySet[Asset]. Passed to
            ``Asset.objects.filter(pk__in=assets)``.
        export_base_dir:
            Directory where the file should be created.

    Raises:
        AssertionError: If an asset has no ``resource_url``.
    """
    asset_resource_file = os.path.join(export_base_dir, "item-resource-urls.txt")

    with open(asset_resource_file, "a") as f:
        distinct_resource_urls = (
            Asset.objects.filter(pk__in=assets)
            .order_by("resource_url")
            .values_list("resource_url", "title")
            .distinct("resource_url")
        )

        for url, title in distinct_resource_urls:
            if url:
                f.write(url)
                f.write("\n")
            else:
                logger.error("No resource URL found for asset %s", title)
                raise AssertionError


def do_bagit_export(
    assets: Iterable[Asset] | QuerySet[Asset],
    export_base_dir: str | Path,
    export_filename_base: str,
    request: HttpRequest | None = None,
) -> HttpResponse | HttpResponseRedirect | List[dict[str, Any]]:
    """
    Build and deliver a BagIt package for ``assets`` or report invalid chars.

    The function validates every asset's ``latest_transcription``. For each
    unacceptable character it records:
    - the asset ID
    - the 1-based line number
    - the 1-based column number
    - the offending character

    Behaviour:
    1. Validation pass: files are written only after a transcription passes
       validation.
    2. Failure(s): any files already written are removed. If ``request`` is
       supplied a template is rendered, otherwise the raw error list is
       returned.
    3. All clear: a BagIt structure is created, zipped and either returned as a
       download or uploaded to S3.

    Args:
        assets:
            Iterable or QuerySet of ``Asset`` to export. Each must have
            ``download_url`` and ``latest_transcription``.
        export_base_dir:
            Temporary directory into which the BagIt hierarchy is built.
        export_filename_base:
            Base name (without ``.zip``) for the archive.
        request:
            Current request. If provided, an error template will be rendered
            when validation fails.

    Returns:
        HttpResponse | HttpResponseRedirect | list[dict[str, Any]]:

        - a download response when packaging locally
        - a redirect to the uploaded archive when S3 is configured
        - a list of validation errors when ``request`` is ``None`` and errors
          were found
    """
    export_base_dir = Path(export_base_dir)
    errors: List[dict[str, Any]] = []

    # Validate every transcription before writing anything to disk
    for asset in assets:
        asset_id = get_original_asset_id(asset.download_url)
        asset_id = asset_id.replace(":", "/")  # BagIt-safe path fragment

        transcription = asset.latest_transcription or ""
        try:
            validate_text_for_export(transcription)
        except UnacceptableCharacterError as err:
            errors.append({"asset": asset, "violations": err.violations})
            continue

        # Passed validation -> write the transcription file
        asset_path, asset_filename = os.path.split(asset_id)
        asset_dest_path = export_base_dir / asset_path
        asset_dest_path.mkdir(parents=True, exist_ok=True)

        if transcription:
            with open(asset_dest_path / f"{asset_filename}.txt", "w") as fp:
                fp.write(transcription)

    # If any errors -> cleanup and report
    if errors:
        if export_base_dir.exists():
            shutil.rmtree(export_base_dir, ignore_errors=True)

        if request is not None:
            return render(
                request,
                "admin/exporter/unacceptable_character_report.html",
                {"errors": errors},
            )
        return errors

    # All assets valid -> create BagIt, zip, upload / return
    write_distinct_asset_resource_file(assets, export_base_dir)

    bagit.make_bag(
        export_base_dir,
        {
            "Content-Access": "web",
            "Content-Custodian": "dcms",
            "Content-Process": "crowdsourced",
            "Content-Type": "textual",
            "LC-Bag-Id": export_filename_base,
            "LC-Items": f"{len(assets)} transcriptions",
            "LC-Project": "gdccrowd",
            "License-Information": "Public domain",
        },
    )

    archive_name = shutil.make_archive(
        str(export_base_dir), "zip", root_dir=export_base_dir
    )
    export_filename = f"{export_filename_base}.zip"

    s3_bucket = getattr(settings, "EXPORT_S3_BUCKET_NAME", None)
    if s3_bucket:
        logger.debug("Uploading exported bag to S3 bucket %s", s3_bucket)
        s3 = boto3.resource("s3")
        s3.Bucket(s3_bucket).upload_file(archive_name, export_filename)

        return HttpResponseRedirect(
            f"https://{s3_bucket}.s3.amazonaws.com/{export_filename}"
        )

    # Local download
    with open(archive_name, "rb") as zip_file:
        response = HttpResponse(zip_file, content_type="application/zip")
    response["Content-Disposition"] = f"attachment; filename={export_filename}"
    return response


class ExportCampaignToCSV(TemplateView):
    """
    Stream a CSV of the most recent transcription for each asset in a campaign.

    Only the latest transcription text per asset is included. Tag values
    are aggregated into a semicolon-delimited string.
    """

    @method_decorator(staff_member_required)
    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """
        Return a CSV response for the requested campaign.

        Args:
            request: Current HTTP request.

        Returns:
            HttpResponse: CSV content for the campaign.
        """
        asset_qs: QuerySet[Asset] = Asset.objects.filter(
            item__project__campaign__slug=self.kwargs["campaign_slug"]
        )
        assets: QuerySet[Asset] = get_latest_transcription_data(asset_qs)
        assets = get_tag_values(assets)

        headers, data = flatten_queryset(
            assets,
            field_names=[
                "item__project__campaign__title",
                "item__project__title",
                "item__title",
                "item__item_id",
                "title",
                "id",
                "transcription_status",
                "download_url",
                "latest_transcription",
                "tag_values",
            ],
            extra_verbose_names={
                "item__project__campaign__title": "Campaign",
                "item__project__title": "Project",
                "item__title": "Item",
                "item__item_id": "ItemId",
                "item_id": "ItemId",
                "title": "Asset",
                "id": "AssetId",
                "transcription_status": "AssetStatus",
                "download_url": "DownloadUrl",
                "latest_transcription": "Transcription",
                "tag_values": "Tags",
            },
        )

        logger.info("Exporting %s to csv", self.kwargs["campaign_slug"])
        return export_to_csv_response(
            "%s.csv" % self.kwargs["campaign_slug"], headers, data
        )


class ExportItemToBagIt(TemplateView):
    """
    Build a BagIt archive for a single item consisting of completed assets.

    Only assets with ``TranscriptionStatus.COMPLETED`` are included.
    """

    @method_decorator(staff_member_required)
    def get(
        self, request: HttpRequest, *args, **kwargs
    ) -> HttpResponse | HttpResponseRedirect:
        """
        Create and return a BagIt archive for the requested item.

        Args:
            request: Current HTTP request.

        Returns:
            HttpResponse | HttpResponseRedirect: Local zip download or redirect
            to S3.
        """
        campaign_slug = self.kwargs["campaign_slug"]
        project_slug = self.kwargs["project_slug"]
        item_id = self.kwargs["item_id"]

        asset_qs: QuerySet[Asset] = Asset.objects.filter(
            item__project__campaign__slug=campaign_slug,
            item__project__slug=project_slug,
            item__item_id=item_id,
            transcription_status=TranscriptionStatus.COMPLETED,
        ).order_by("sequence")

        assets: QuerySet[Asset] = get_latest_transcription_data(asset_qs)

        campaign = Campaign.objects.get(slug__exact=campaign_slug)
        campaign_slug_dbv = campaign.slug
        project = Project.objects.get(campaign=campaign, slug__exact=project_slug)
        project_slug_dbv = project.slug
        item_id_dbv = Item.objects.get(item_id__exact=item_id).item_id

        export_filename_base = "%s-%s-%s" % (
            campaign_slug_dbv,
            project_slug_dbv,
            item_id_dbv,
        )

        with tempfile.TemporaryDirectory(
            prefix=export_filename_base
        ) as export_base_dir:
            return do_bagit_export(
                assets, export_base_dir, export_filename_base, request
            )


class ExportProjectToBagIt(TemplateView):
    """
    Build a BagIt archive for a project consisting of completed items only.
    """

    @method_decorator(staff_member_required)
    def get(
        self, request: HttpRequest, *args, **kwargs
    ) -> HttpResponse | HttpResponseRedirect:
        """
        Create and return a BagIt archive for the requested project.

        Args:
            request: Current HTTP request.

        Returns:
            HttpResponse | HttpResponseRedirect: Local zip download or redirect
            to S3.
        """
        campaign_slug = self.kwargs["campaign_slug"]
        project_slug = self.kwargs["project_slug"]

        item_qs: QuerySet[Item] = Item.objects.filter(
            project__campaign__slug=campaign_slug, project__slug=project_slug
        )
        asset_qs: QuerySet[Asset] = remove_incomplete_items(item_qs)
        assets: QuerySet[Asset] = get_latest_transcription_data(asset_qs)

        campaign = Campaign.objects.get(slug__exact=campaign_slug)
        campaign_slug_dbv = campaign.slug
        project = Project.objects.get(campaign=campaign, slug__exact=project_slug)
        project_slug_dbv = project.slug

        export_filename_base = "%s-%s" % (campaign_slug_dbv, project_slug_dbv)

        with tempfile.TemporaryDirectory(
            prefix=export_filename_base
        ) as export_base_dir:
            return do_bagit_export(
                assets, export_base_dir, export_filename_base, request
            )


class ExportCampaignToBagIt(TemplateView):
    """
    Build a BagIt archive for a campaign consisting of completed items only.
    """

    @method_decorator(staff_member_required)
    def get(
        self, request: HttpRequest, *args, **kwargs
    ) -> HttpResponse | HttpResponseRedirect:
        """
        Create and return a BagIt archive for the requested campaign.

        Args:
            request: Current HTTP request.

        Returns:
            HttpResponse | HttpResponseRedirect: Local zip download or redirect
            to S3.
        """
        campaign_slug = self.kwargs["campaign_slug"]

        item_qs: QuerySet[Item] = Item.objects.filter(
            project__campaign__slug=campaign_slug
        )
        asset_qs: QuerySet[Asset] = remove_incomplete_items(item_qs)
        assets: QuerySet[Asset] = get_latest_transcription_data(asset_qs)

        campaign_slug_dbv = Campaign.objects.get(slug__exact=campaign_slug).slug

        export_filename_base = "%s" % (campaign_slug_dbv,)

        with tempfile.TemporaryDirectory(
            prefix=export_filename_base
        ) as export_base_dir:
            return do_bagit_export(
                assets, export_base_dir, export_filename_base, request
            )


class ExportProjectToCSV(TemplateView):
    """
    Stream a CSV of the most recent transcription for each asset in a project.

    Only the latest transcription text per asset is included. Tag values
    are aggregated into a semicolon-delimited string.
    """

    @method_decorator(staff_member_required)
    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """
        Return a CSV response for the requested project.

        Args:
            request: Current HTTP request.

        Returns:
            HttpResponse: CSV content for the project.
        """
        campaign_slug = self.kwargs["campaign_slug"]
        project_slug = self.kwargs["project_slug"]

        campaign = Campaign.objects.get(slug__exact=campaign_slug)
        project = Project.objects.get(campaign=campaign, slug__exact=project_slug)

        asset_qs: QuerySet[Asset] = Asset.objects.filter(item__project=project)
        assets: QuerySet[Asset] = get_latest_transcription_data(asset_qs)
        assets = get_tag_values(assets)

        headers, data = flatten_queryset(
            assets,
            field_names=[
                "item__project__campaign__title",
                "item__project__title",
                "item__title",
                "item__item_id",
                "title",
                "id",
                "transcription_status",
                "download_url",
                "latest_transcription",
                "tag_values",
            ],
            extra_verbose_names={
                "item__project__campaign__title": "Campaign",
                "item__project__title": "Project",
                "item__title": "Item",
                "item__item_id": "ItemId",
                "item_id": "ItemId",
                "title": "Asset",
                "id": "AssetId",
                "transcription_status": "AssetStatus",
                "download_url": "DownloadUrl",
                "latest_transcription": "Transcription",
                "tag_values": "Tags",
            },
        )

        logger.info("Exporting %s to csv", self.kwargs["project_slug"])
        return export_to_csv_response(
            f"{campaign.slug}-{project.slug}.csv", headers, data
        )
