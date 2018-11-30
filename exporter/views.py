import os
import re
import shutil
import tempfile
from logging import getLogger

import bagit
import boto3
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import OuterRef, Subquery
from django.http import HttpResponse, HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from tabular_export.core import export_to_csv_response, flatten_queryset

from concordia.models import Asset, Transcription

logger = getLogger(__name__)


def get_latest_transcription_data(asset_qs):
    latest_trans_subquery = (
        Transcription.objects.filter(asset=OuterRef("pk"))
        .order_by("-pk")
        .values("text")
    )

    assets = asset_qs.annotate(latest_transcription=Subquery(latest_trans_subquery[:1]))
    return assets


def get_original_asset_id(download_url):
    """
    Extract the bit from the download url
    that identifies this image uniquely on loc.gov
    """
    if download_url.startswith("http://tile.loc.gov/"):
        pattern = r"/service:([A-Za-z0-9:\-]+)/"
        asset_id = re.search(pattern, download_url).group(1)
        assert asset_id
        logger.debug("Found asset ID %s in download URL %s", asset_id, download_url)
        return asset_id
    else:
        logger.warning(
            "Download URL doesn't start with tile.loc.gov: %s" % download_url
        )
        return download_url


def do_bagit_export(assets, export_base_dir, export_filename_base):
    """
    Executes bagit.py to turn temp directory into LC-specific bagit strucutre.
    Builds and exports bagit structure as zip.
    Uploads zip to S3 if configured.
    """

    for asset in assets:
        asset_id = get_original_asset_id(asset.download_url)
        logger.debug("Exporting asset %s into %s" % (asset_id, export_base_dir))

        asset_id = asset_id.replace(":", "/")
        asset_path, asset_filename = os.path.split(asset_id)

        dest_path = os.path.join(export_base_dir, asset_path)
        os.makedirs(dest_path, exist_ok=True)

        # Build transcription output text file
        text_output_path = os.path.join(dest_path, "%s.txt" % asset_filename)
        with open(text_output_path, "w") as f:
            f.write(asset.latest_transcription or "")

    # Turn Structure into bagit format
    bagit.make_bag(
        export_base_dir,
        {
            "Content-Access": "web",
            "Content-Custodian": "dcms",
            "Content-Process": "crowdsourcing",
            "Content-Type": "textual",
            "LC-Bag-Id": export_filename_base,
            "LC-Items": "%d transcriptions" % len(assets),
            "LC-Project": "gdccrowd",
            "License-Information": "Public domain",
        },
    )

    # Build .zip file of bagit formatted Campaign Folder
    archive_name = export_base_dir
    shutil.make_archive(archive_name, "zip", export_base_dir)

    export_filename = "%s.zip" % export_filename_base

    # Upload zip to S3 bucket
    s3_bucket = getattr(settings, "EXPORT_S3_BUCKET_NAME", None)

    if s3_bucket:
        logger.debug("Uploading exported bag to S3 bucket %s", s3_bucket)
        s3 = boto3.resource("s3")
        s3.Bucket(s3_bucket).upload_file(
            "%s.zip" % export_base_dir, "%s" % export_filename
        )

        return HttpResponseRedirect(
            "https://%s.s3.amazonaws.com/%s" % (s3_bucket, export_filename)
        )
    else:
        # Download zip from local storage
        with open("%s.zip" % export_base_dir, "rb") as zip_file:
            response = HttpResponse(zip_file, content_type="application/zip")
        response["Content-Disposition"] = "attachment; filename=%s" % export_filename
        return response


class ExportCampaignToCSV(TemplateView):
    """
    Exports the most recent transcription for each asset in a campaign
    """

    @method_decorator(staff_member_required)
    def get(self, request, *args, **kwargs):
        asset_qs = Asset.objects.filter(
            item__project__campaign__slug=self.kwargs["campaign_slug"]
        )
        assets = get_latest_transcription_data(asset_qs)

        headers, data = flatten_queryset(
            assets,
            field_names=[
                "item__project__campaign__title",
                "item__project__title",
                "item__title",
                "item__item_id",
                "title",
                "transcription_status",
                "download_url",
                "latest_transcription",
            ],
            extra_verbose_names={
                "item__project__campaign__title": "Campaign",
                "item__project__title": "Project",
                "item__title": "Item",
                "item__item_id": "ItemId",
                "item_id": "ItemId",
                "title": "Asset",
                "transcription_status": "AssetStatus",
                "download_url": "DownloadUrl",
                "latest_transcription": "Transcription",
            },
        )

        return export_to_csv_response(
            "%s.csv" % self.kwargs["campaign_slug"], headers, data
        )


class ExportItemToBagIt(TemplateView):
    @method_decorator(staff_member_required)
    def get(self, request, *args, **kwargs):
        campaign_slug = self.kwargs["campaign_slug"]
        project_slug = self.kwargs["project_slug"]
        item_id = self.kwargs["item_id"]

        asset_qs = Asset.objects.filter(
            item__project__campaign__slug=campaign_slug,
            item__project__slug=project_slug,
            item__item_id=item_id,
            transcription_status="completed",
        )

        assets = get_latest_transcription_data(asset_qs)

        export_filename_base = "%s-%s-%s" % (campaign_slug, project_slug, item_id)

        with tempfile.TemporaryDirectory(
            prefix=export_filename_base
        ) as export_base_dir:
            return do_bagit_export(assets, export_base_dir, export_filename_base)


class ExportProjectToBagIt(TemplateView):
    @method_decorator(staff_member_required)
    def get(self, request, *args, **kwargs):
        campaign_slug = self.kwargs["campaign_slug"]
        project_slug = self.kwargs["project_slug"]
        asset_qs = Asset.objects.filter(
            item__project__campaign__slug=campaign_slug,
            item__project__slug=project_slug,
            transcription_status="completed",
        )

        assets = get_latest_transcription_data(asset_qs)

        export_filename_base = "%s-%s" % (campaign_slug, project_slug)

        with tempfile.TemporaryDirectory(
            prefix=export_filename_base
        ) as export_base_dir:
            return do_bagit_export(assets, export_base_dir, export_filename_base)


class ExportCampaignToBagit(TemplateView):
    @method_decorator(staff_member_required)
    def get(self, request, *args, **kwargs):
        campaign_slug = self.kwargs["campaign_slug"]
        asset_qs = Asset.objects.filter(
            item__project__campaign__slug=campaign_slug,
            transcription_status="completed",
        )

        assets = get_latest_transcription_data(asset_qs)

        export_filename_base = "%s" % (campaign_slug,)

        with tempfile.TemporaryDirectory(
            prefix=export_filename_base
        ) as export_base_dir:
            return do_bagit_export(assets, export_base_dir, export_filename_base)
