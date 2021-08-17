import os
import re
import shutil
import tempfile
from logging import getLogger
import sys
import csv
import json
import requests
import time

import bagit
import boto3
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import OuterRef, Subquery
from django.http import HttpResponse, HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from tabular_export.core import export_to_csv_response, flatten_queryset

from concordia.models import Asset, Item, Transcription, TranscriptionStatus

logger = getLogger(__name__)

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
    if 'status' in loc_json and loc_json['status'] == 404:
        return 404
    return loc_json

# Return the Item JSON for a loc.gov /item
def locgov_item(item, locgov_server):
    url_start = 'https://%s.loc.gov/item/' % locgov_server
    url = url_start + item + '/?fo=json&at=item'
    item_json = get_locgov_json(url)
    if item_json == 404:
        return 404
    return item_json['item']

# Returns the Resources given an Item URL
# This should have file data for all files in all of the item's resources
def locgov_item_resources(item, locgov_server):
    url_start = 'https://%s.loc.gov/item/' % locgov_server
    url = url_start + item + '/?fo=json&at=resources'
    resources_json = get_locgov_json(url, "www")
    if resources_json == 404:
        return 404
    return resources_json['resources']

# Get the Item for a given Resource
def locgov_resource_item_section(resource, locgov_server):
    if not resource.endswith('/'):
        resource = resource + '/'
    url = resource + '?fo=json&at=item'
    item_json = get_locgov_json(url, locgov_server)

    if item_json == 404:
        return 404
    return item_json['item']

# Script to generate concatinated transcription files, and make resource dirs for receive to CTS
# Run script in data directory
# at same level as item-resource-urls.txt

def locgov_create_resources(resource_dir):

    #cwd = os.getcwd()
    cwd = resource_dir
    item_file = os.path.join(cwd, 'item-resource-urls.txt')

    # resource for txt looks like = 'http://www.loc.gov/resource/mss85943.002514/'

    # Resource TXT file has repeated rows - get all unique Resource URLS
    resource_urls = []
    with open(item_file, 'r', encoding='utf-8') as item_txt:
        for line in item_txt:
            r = line.strip()
            if r not in resource_urls:
                resource_urls.append(r)

    for resource in resource_urls:
        resource_id = resource.split('/')[-2]

        # Filename of concat file will be last section of Resource URL, after the period
        concat_filename = resource.rsplit('.', 1)[-1].replace('/', '') + '.txt'

        # Get the item for the resource - stored in item['id']
        item = locgov_resource_item_section(resource, 'www')
        # item_id = item['id']  #when ['item']['id'] is a item id (not a loc.gov/item url)
        item_id = item['id'].split('/')[-2]  #when ['item']['id'] is a loc.gov/item url (not item id)

        # Get the resources for that item, and find the resource that is this resource
        # (May be multiple resources per item)
        # Get the files list for that resource
        resources = locgov_item_resources(item_id, 'www')
        for r in resources:
            if resource_id in r['url']:
                files = r['files']

        # Get the expected list of text files matching each TIFF from the files list
        # Text file should be located at filepath matching TIFF after /master
        txt_files = []
        for f in files:
            for s in f:
                if s['mimetype'] == 'image/tiff':
                    txt_files.append(s['url'].rsplit('/master', 1)[-1].replace('.tif', '.txt'))

        # Path to new concat_file - filepath of first text file, minus the filename of that file,
        #  adding on concat_filename
        concat_file = cwd + txt_files[0].rsplit('/', 1)[0] + '/' + concat_filename

        # Open/create the concat file, append each txt file, if it exists
        # (Some txt files may not exist because there was no content to transcribe)
        # Each line from txt appended, unless it contains 'crowd.loc.gov'
        with open(concat_file, 'w', encoding='utf-8') as concat_write:
            attribution = ''
            for t in txt_files:
                trans_file = cwd + t
                if os.path.isfile(trans_file):
                    with open(trans_file, 'r', encoding='utf-8') as trans_file:
                        for l in trans_file:
                            if 'crowd.loc.gov' in l:
                                attribution = l
                                continue
                            else:
                                concat_write.write(l)
            concat_write.write(attribution)

        # Make resource dir if it does not exist - named by resource id, swapping . for -
        # copy in concat file
        resource_dir = cwd + '/' + resource_id.replace('.', '-')
        if not os.path.isdir(resource_dir):
            os.mkdir(resource_dir)
            print('making dir: ', resource_dir)
        new_concat_file = resource_dir + '/' + concat_filename
        copy = concat_file + ' -> ' + new_concat_file
        shutil.copyfile(concat_file, new_concat_file)

        # copy all of the resource's txt files into the new resource dir
        for t in txt_files:
            trans_file = cwd + t
            trans_filename = t.rsplit('/', 1)[-1]
            new_trans_file = resource_dir + '/' + trans_filename
            if os.path.isfile(trans_file):
                copy = trans_file + ' -> ' + new_trans_file
                shutil.copyfile(trans_file, new_trans_file)


def get_latest_transcription_data(asset_qs):
    latest_trans_subquery = (
        Transcription.objects.filter(asset=OuterRef("pk"))
        .order_by("-pk")
        .values("text")
    )

    assets = asset_qs.annotate(latest_transcription=Subquery(latest_trans_subquery[:1]))
    return assets


def remove_incomplete_items(item_qs):
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


def get_original_asset_id(download_url):
    """
    Extract the bit from the download url
    that identifies this image uniquely on loc.gov
    """
    download_url = download_url.replace("https", "http")
    if download_url.startswith("http://tile.loc.gov/"):
        pattern = r"/service:([A-Za-z0-9:.\-\_]+)/|/master/([A-Za-z0-9/]+)/"
        asset_id = re.search(pattern, download_url)
        if not asset_id:
            logger.error(
                "Couldn't find a matching asset ID in download URL %s", download_url
            )
            raise AssertionError
        else:
            if asset_id.group(1):
                matching_asset_id = asset_id.group(1)
            else:
                matching_asset_id = asset_id.group(2)
            logger.debug(
                "Found asset ID %s in download URL %s", matching_asset_id, download_url
            )
            return matching_asset_id
    else:
        logger.warning("Download URL doesn't start with tile.loc.gov: %s", download_url)
        return download_url


def write_item_resource_file(assets, export_base_dir):
    item_resource_file = os.path.join(export_base_dir, "item-resource-urls.txt")

    with open(item_resource_file, "a") as f:

        # Find the URL for the item that starts with http://www.loc.gov/resource/
        items = Item.objects.filter(asset__in=assets)

        for item in items:
            item_resource_url = ""
            if item.metadata:
                for item_url in item.metadata["item"]["aka"]:
                    if "http://www.loc.gov/resource/" in item_url:
                        item_resource_url = item_url
                        break

                if item_resource_url != "":
                    f.write(item_resource_url)
                    f.write("\n")
                else:
                    logger.error(
                        "Could not determine item resource URL for item %s",
                        item.item_id,
                    )
                    raise AssertionError


def do_bagit_export(assets, export_base_dir, export_filename_base):
    """
    Executes bagit.py to turn temp directory into LC-specific bagit strucutre.
    Builds and exports bagit structure as zip.
    Uploads zip to S3 if configured.
    """

    # These assets should already be in the correct order - by item, seequence
    for asset in assets:
        asset_id = get_original_asset_id(asset.download_url)
        logger.debug("Exporting asset %s into %s", asset_id, export_base_dir)

        asset_id = asset_id.replace(":", "/")
        asset_path, asset_filename = os.path.split(asset_id)

        asset_dest_path = os.path.join(export_base_dir, asset_path)
        os.makedirs(asset_dest_path, exist_ok=True)

        # Build a transcription output text file for each asset
        asset_text_output_path = os.path.join(
            asset_dest_path, "%s.txt" % asset_filename
        )

        if asset.latest_transcription:
            # Write the asset level transcription file
            with open(asset_text_output_path, "w") as f:
                f.write(asset.latest_transcription)

    # Add attributions to the end of all text files found under asset_dest_path
    if hasattr(settings, "ATTRIBUTION_TEXT"):
        for dirpath, _, filenames in os.walk(export_base_dir, topdown=False):
            for each_text_file in (i for i in filenames if i.endswith(".txt")):
                this_text_file = os.path.join(dirpath, each_text_file)
                with open(this_text_file, "a") as f:
                    f.write("\n\n")
                    f.write(settings.ATTRIBUTION_TEXT)

    write_item_resource_file(assets, export_base_dir)

    # Turn Structure into bagit format
    bagit.make_bag(
        export_base_dir,
        {
            "Content-Access": "web",
            "Content-Custodian": "dcms",
            "Content-Process": "crowdsourced",
            "Content-Type": "textual",
            "LC-Bag-Id": export_filename_base,
            "LC-Items": "%d transcriptions" % len(assets),
            "LC-Project": "gdccrowd",
            "License-Information": "Public domain",
        },
    )

    export_dir = export_base_dir + "/data"
    locgov_create_resources(export_dir)
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
            transcription_status=TranscriptionStatus.COMPLETED,
        ).order_by("sequence")

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

        item_qs = Item.objects.filter(
            project__campaign__slug=campaign_slug, project__slug=project_slug
        )
        asset_qs = remove_incomplete_items(item_qs)
        assets = get_latest_transcription_data(asset_qs)

        export_filename_base = "%s-%s" % (campaign_slug, project_slug)

        with tempfile.TemporaryDirectory(
            prefix=export_filename_base
        ) as export_base_dir:
            return do_bagit_export(assets, export_base_dir, export_filename_base)


class ExportCampaignToBagIt(TemplateView):
    @method_decorator(staff_member_required)
    def get(self, request, *args, **kwargs):
        campaign_slug = self.kwargs["campaign_slug"]

        item_qs = Item.objects.filter(project__campaign__slug=campaign_slug)
        asset_qs = remove_incomplete_items(item_qs)
        assets = get_latest_transcription_data(asset_qs)

        export_filename_base = "%s" % (campaign_slug,)

        with tempfile.TemporaryDirectory(
            prefix=export_filename_base
        ) as export_base_dir:
            return do_bagit_export(assets, export_base_dir, export_filename_base)
