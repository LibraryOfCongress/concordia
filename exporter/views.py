import os
import shutil

import bagit
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Subquery, OuterRef
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from tabular_export.core import export_to_csv_response, flatten_queryset

from concordia.models import Asset, Campaign, Transcription
from concordia.storage import ASSET_STORAGE


class ExportCampaignToCSV(TemplateView):
    """
    Exports the most recent transcription for each asset in a campaign

    """

    @method_decorator(login_required)
    def get(self, request, *args, **kwargs):
        latest_trans_subquery = (
            Transcription.objects.filter(asset=OuterRef("pk"))
            .order_by("-pk")
            .values("text")
        )
        assets = Asset.objects.annotate(
            latest_transcription=Subquery(latest_trans_subquery[:1])
        )
        assets = assets.filter(
            item__project__campaign__slug=self.kwargs["campaign_slug"]
        )

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


class ExportCampaignToBagit(TemplateView):
    """
    Creates temp directory structure for source data.  Copies source image
    file from S3 or local storage into temp directory, builds export.csv
    with meta, transcription, and tag data.  Executes bagit.py to turn temp
    directory into bagit strucutre.  Builds and exports bagit structure as
    zip.  Removes all temporary directories and files.

    """

    include_images = True
    template_name = "transcriptions/campaign.html"

    @method_decorator(login_required)
    def get(self, request, *args, **kwargs):
        campaign = Campaign.objects.get(slug=self.kwargs["campaign_slug"])
        asset_list = Asset.objects.filter(item__project__campaign=campaign).order_by(
            "title", "sequence"
        )

        # FIXME: this code should be working in a separate path than the media root!
        # FIXME: we should be able to export at the project and item level, too
        export_base_dir = os.path.join(settings.MEDIA_ROOT, "exporter", campaign.slug)

        for asset in asset_list:
            src = os.path.join(
                settings.MEDIA_ROOT,
                asset.item.project.campaign.slug,
                asset.item.project.slug,
                asset.item.item_id,
                asset.slug,
                asset.media_url,
            )
            dest_folder = os.path.join(
                export_base_dir, asset.item.project.slug, asset.item.item_id, asset.slug
            )
            os.makedirs(dest_folder, exist_ok=True)
            dest = os.path.join(dest_folder, asset.media_url)

            if self.include_images:
                with open(dest, mode="wb") as dest_file:
                    with ASSET_STORAGE.open(src, mode="rb") as src_file:
                        for chunk in src_file.chunks(1048576):
                            dest_file.write(chunk)

            # Get transcription data
            # FIXME: if we're not including all transcriptions,
            # we should pick the completed or latest versions!

            try:
                transcription = Transcription.objects.get(
                    asset=asset, user=self.request.user
                ).text
            except Transcription.DoesNotExist:
                transcription = ""

            # Build transcription output text file
            tran_output_path = os.path.join(
                dest_folder, "%s.txt" % os.path.basename(asset.media_url)
            )
            with open(tran_output_path, "w") as f:
                f.write(transcription)

        # Turn Structure into bagit format
        bagit.make_bag(export_base_dir, {"Contact-Name": request.user.username})

        # Build .zip file of bagit formatted Campaign Folder
        archive_name = export_base_dir
        shutil.make_archive(archive_name, "zip", export_base_dir)

        # Download zip
        with open("%s.zip" % export_base_dir, "rb") as zip_file:
            response = HttpResponse(zip_file, content_type="application/zip")
        response["Content-Disposition"] = "attachment; filename=%s.zip" % campaign.slug

        # Clean up temp folders & zipfile once exported
        shutil.rmtree(export_base_dir)
        os.remove("%s.zip" % export_base_dir)

        return response
