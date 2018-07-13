import csv
import os
import shutil
from shutil import copyfile

import bagit
from django.conf import settings
from django.http import HttpResponse
from django.views.generic import TemplateView

from concordia.models import Collection, Transcription, UserAssetTagCollection


class ExportCollectionToCSV(TemplateView):
    """
    Exports the transcription and tags to csv file

    """

    template_name = "transcriptions/collection.html"

    def get(self, request, *args, **kwargs):
        collection = Collection.objects.get(slug=self.args[0])
        asset_list = collection.asset_set.all().order_by("title", "sequence")
        # Create the HttpResponse object with the appropriate CSV header.
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="{0}.csv"'.format(
            collection.slug
        )
        field_names = ["title", "description", "media_url"]
        writer = csv.writer(response)
        writer.writerow(
            ["Collection", "Title", "Description", "MediaUrl", "Transcription", "Tags"]
        )
        for asset in asset_list:
            transcription = Transcription.objects.filter(
                asset=asset, user_id=self.request.user.id
            )
            if transcription:
                transcription = transcription[0].text
            else:
                transcription = ""
            tags = UserAssetTagCollection.objects.filter(
                asset=asset, user_id=self.request.user.id
            )
            if tags:
                tags = list(tags[0].tags.all().values_list("name", flat=True))
            else:
                tags = ""
            row = (
                [collection.title]
                + [getattr(asset, i) for i in field_names]
                + [transcription, tags]
            )
            writer.writerow(row)
        return response


class ExportCollectionToBagit(TemplateView):
    """
    Creates temp directory structure for source data.  Moves source image
    file into temp directory, builds export.csv with meta, transcription,
    and tag data.  Executes bagit.py to turn temp directory into bagit
    strucutre.  Builds and exports bagit structure as zip.  Removes all
    temporary directories and files.

    """

    template_name = "transcriptions/collection.html"

    def get(self, request, *args, **kwargs):
        collection = Collection.objects.get(slug=self.args[0])
        asset_list = collection.asset_set.all().order_by("title", "sequence")

        # Make sure export folder exists (media/exporter)
        export_folder = "%s/exporter" % (settings.MEDIA_ROOT)
        if not os.path.exists(export_folder):
            os.makedirs(export_folder)

        # Create temp exporter folder structure in media for bagit
        collection_folder = "%s/exporter/%s" % (settings.MEDIA_ROOT, collection.slug)

        # Create collection folder (media/exporter/<collection>)
        if not os.path.exists(collection_folder):
            os.mkdir(collection_folder)

        for asset in asset_list:
            asset_folder = "%s/%s" % (collection_folder, asset.slug)

            # Create asset folders (media/exporter/<collection>/<asset>
            if not os.path.exists(asset_folder):
                os.mkdir(asset_folder)

            src_folder = asset_folder.replace("exporter", "concordia")
            src_name = asset.media_url.rsplit("/")[-1]
            src = "%s/%s" % (src_folder, src_name)
            dest = "%s/%s" % (asset_folder, src_name)

            # Copy assest image file into asset folder
            copyfile(src, dest)

            # Build export.csv with asset meta data, transcription & tag info
            csv_dest = "%s/export.csv" % asset_folder
            with open(csv_dest, "w") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(
                    [
                        "Collection",
                        "Title",
                        "Description",
                        "MediaUrl",
                        "Transcription",
                        "Tags",
                    ]
                )

                field_names = ["title", "description", "media_url"]
                transcription = Transcription.objects.filter(
                    asset=asset, user_id=self.request.user.id
                )
                if transcription:
                    transcription = transcription[0].text
                else:
                    transcription = ""

                tags = UserAssetTagCollection.objects.filter(
                    asset=asset, user_id=self.request.user.id
                )
                if tags:
                    tags = list(tags[0].tags.all().values_list("name", flat=True))
                else:
                    tags = ""

                row = (
                    [collection.title]
                    + [getattr(asset, i) for i in field_names]
                    + [transcription, tags]
                )
                writer.writerow(row)

        # Turn Strucutre into bagit format
        bag = bagit.make_bag(collection_folder, {"Contact-Name": request.user.username})

        # Build .zipfile of bagit formatted Collection Folder
        archive_name = collection_folder
        shutil.make_archive(archive_name, "zip", collection_folder)

        # Download zip
        with open("%s.zip" % collection_folder, "rb") as file:
            outfile = file.read()
        response = HttpResponse(outfile, content_type="application/zip")
        response["Content-Disposition"] = (
            "attachment; filename=%s.zip" % collection.slug
        )

        # Clean up temp folders & zipfile once exported
        try:
            shutil.rmtree(collection_folder)
        except:
            pass
        try:
            os.remove("%s.zip" % collection_folder)
        except:
            pass

        return response
