import os
import re
import shutil

import bagit
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Subquery, OuterRef
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from tabular_export.core import export_to_csv_response, flatten_queryset

from concordia.models import Asset, Transcription


def get_latest_transcription_data(campaign_slug):
    latest_trans_subquery = (
        Transcription.objects.filter(asset=OuterRef("pk"))
        .order_by("-pk")
        .values("text")
    )
    assets = Asset.objects.annotate(
        latest_transcription=Subquery(latest_trans_subquery[:1])
    )
    assets = assets.filter(item__project__campaign__slug=campaign_slug)
    return assets


def get_original_asset_id(download_url):
    """
    Extract the bit from the download url
    that identifies this image uniquely on loc.gov
    """
    if download_url.startswith("http://tile.loc.gov/"):
        pattern = r"/service:([A-Za-z0-9:]*)/"
        asset_id = re.search(pattern, download_url)
        assert asset_id
        return asset_id.group(1).replace(":", "-")
    else:
        return download_url


class ExportCampaignToCSV(TemplateView):
    """
    Exports the most recent transcription for each asset in a campaign
    """

    @method_decorator(login_required)
    def get(self, request, *args, **kwargs):
        assets = get_latest_transcription_data(self.kwargs["campaign_slug"])

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


# FIXME: we should be able to export at the project and item level, too
class ExportCampaignToBagit(TemplateView):
    """
    Creates temp directory structure for source data.
    Executes bagit.py to turn temp directory into bagit strucutre.
    Builds and exports bagit structure as zip.
    Removes all temporary directories and files.
    """

    @method_decorator(login_required)
    def get(self, request, *args, **kwargs):
        campaign_slug = self.kwargs["campaign_slug"]
        assets = get_latest_transcription_data(campaign_slug)

        export_base_dir = os.path.join(settings.SITE_ROOT_DIR, "tmp", campaign_slug)

        for asset in assets:
            dest_folder = os.path.join(
                export_base_dir, asset.item.project.slug, asset.item.item_id
            )
            os.makedirs(dest_folder, exist_ok=True)

            # Build transcription output text file
            text_output_path = os.path.join(
                dest_folder,
                "%s.txt" % os.path.basename(get_original_asset_id(asset.download_url)),
            )
            with open(text_output_path, "w") as f:
                f.write(asset.latest_transcription or "")

        # Turn Structure into bagit format
        bagit.make_bag(export_base_dir, {"Contact-Name": request.user.username})

        # Build .zip file of bagit formatted Campaign Folder
        archive_name = export_base_dir
        shutil.make_archive(archive_name, "zip", export_base_dir)

        # Download zip
        with open("%s.zip" % export_base_dir, "rb") as zip_file:
            response = HttpResponse(zip_file, content_type="application/zip")
        response["Content-Disposition"] = "attachment; filename=%s.zip" % campaign_slug

        # Upload zip to S3 bucket

        # Clean up temp folders & zipfile once exported
        shutil.rmtree(export_base_dir)
        os.remove("%s.zip" % export_base_dir)

        return response
