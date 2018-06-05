from __future__ import absolute_import, unicode_literals
import requests
import os
import sys
from urllib.parse import urlparse
import boto3
import botocore
from PIL import Image
import logging

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(PROJECT_DIR)

sys.path.append(BASE_DIR)

sys.path.append(os.path.join(BASE_DIR, "config"))
from config import Config


# TODO: use util to import Config


class Importer:
    # Config loaded from Django settings
    base_url = ""
    item_count = 0
    images_folder = ""
    s3_bucket_name = ""

    # Constants
    MIME_TYPE = "image/jpeg"
    COLLECTION_PAGINATION = 25
    IMAGE_CHUNK_SIZE = 100000
    ITEM_URL_FORMAT = "https://www.loc.gov/item/{0}"

    # Ephemeral data
    collection_data = {}

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        self.base_url = Config.Get("importer")["BASE_URL"]
        self.item_count = 10  # Config.Get('importer')['ITEM_COUNT']
        self.images_folder = (
            "/concordia_images"
        )  # Config.Get('importer')['IMAGES_FOLDER']
        self.s3_bucket_name = Config.Get("importer")["S3_BUCKET_NAME"]

    def main(self):
        self.get_and_save_images(self.base_url)
        self.check_total_item_count()

    def download_collection(self, collection_url, item_count):
        self.base_url = collection_url
        self.item_count = item_count
        self.main()

    def download_item(self, item_identifier):
        self.get_item_images(item_identifier)

    def check_completeness(self):
        # Checks for total number of items and number of images per item
        # Returns True if the entire collection has been downloaded
        have_all_items = self.check_total_item_count()

        if have_all_items:
            # Make sure the items have the correct number of images per directory.
            for item_folder in os.listdir(self.images_folder):
                if not self.check_item_folder_completeness(item_folder):
                    return False
            return True
        else:
            return False

    def check_collection_completeness(self, collection_url, item_count):
        self.base_url = collection_url
        self.item_count = item_count

        self.check_completeness()

    def check_total_item_count(self):
        # Check that the total number of items matches the expected number of total items
        actual_item_count = len(os.listdir(self.images_folder))

        if actual_item_count < int(self.item_count):
            self.logger.error(
                "Expected item count %(item_count)d but actual item count of "
                "%(images_folder)s is %(actual_item_count)d",
                {
                    "item_count": self.item_count,
                    "images_folder": self.images_folder,
                    "actual_item_count": actual_item_count,
                },
            )
            return False
        else:
            return True

    def check_item_folder_completeness(self, item_id):
        item_url = self.ITEM_URL_FORMAT.format(item_id)
        image_files = self.get_item_image_files(item_url)
        expected_image_count = len(image_files)
        actual_image_count = len(os.listdir(os.path.join(self.images_folder, item_id)))
        if expected_image_count != actual_image_count:
            self.logger.error(
                "Item %(item_id)s is expected to have %(expected_image_count)d images "
                "but actually has %(actual_image_count)d images",
                {
                    "item_id": item_id,
                    "expected_image_count": expected_image_count,
                    "actual_image_count": actual_image_count,
                },
            )
            return False
        else:
            self.logger.info(
                "Item %(item_id)s has the expected number of %(image_count)d images",
                {"item_id": item_id, "image_count": actual_image_count},
            )
            return True

    @staticmethod
    def check_item_image_exists(filename):
        # Check whether filename exists
        if os.path.exists(filename):
            return True
        else:
            return False

    def verify_item_image(self, filename, identifier, image_number):
        try:
            image_file = Image.open(filename)
            actual_width, actual_height = image_file.size
            self.logger.debug(
                "Actual width and height of %(filename)s are %(width)d and %(height)d respectively",
                {"filename": filename, "width": actual_width, "height": actual_height},
            )

            image_file.verify()
            self.logger.debug("Completed verification of %s", filename)

            # check image width and height and verify that it matches the expected sizes
            expected_width = self.collection_data[identifier]["image_sizes"][
                image_number
            ]["width"]
            expected_height = self.collection_data[identifier]["image_sizes"][
                image_number
            ]["height"]
            self.logger.debug(
                "Expected width and height of %(filename)s are %(width)d and %(height)d respectively",
                {
                    "filename": filename,
                    "width": expected_width,
                    "height": expected_height,
                },
            )

            if (
                actual_width != expected_width
                and abs(actual_width - expected_width) > 1
            ):
                self.logger.error(
                    "Expected width of %(width)d but actual image width is %(actual_width)d",
                    {"width": expected_width, "actual_width": actual_width},
                )
                return False

            if (
                actual_height != expected_height
                and abs(actual_width - expected_width) > 1
            ):
                self.logger.error(
                    "Expected height of %(height)d but actual image height is %(actual_height)d",
                    {"height": expected_height, "actual_height": actual_height},
                )
                return False
        except IOError:
            self.logger.error(
                "An exception occurred attempting to verify %s", filename, exc_info=True
            )
            return False

        return True

    def write_image_file(self, image, filename, identifier, image_number):
        # Check if we already have this image on disk
        if not self.check_item_image_exists(filename):
            # Request the image and write it to filename
            image_url = image
            self.logger.info("Requesting %s", image_url)
            image_response = requests.get(image_url, stream=True)
            with open(filename, "wb") as fd:
                for chunk in image_response.iter_content(
                    chunk_size=self.IMAGE_CHUNK_SIZE
                ):
                    fd.write(chunk)
                    self.logger.debug(
                        "Writing another %d size chunk", self.IMAGE_CHUNK_SIZE
                    )

            self.logger.info("Finished writing the image file %s", filename)

        # If the image successfully verifies, upload it to the S3 bucket
        if self.verify_item_image(filename, identifier, image_number):
            if self.s3_bucket_name:
                image_stats = os.stat(filename)
                size_on_disk = image_stats.st_size
                if not self.check_image_file_on_s3(filename, size_on_disk):
                    s3 = boto3.client("s3")
                    # TODO: If the s3 bucket doesn't exist yet, try to create it
                    # TODO: Queue the S3 uploads so they can occur asynchronously
                    s3.upload_file(filename, self.s3_bucket_name, filename)
                    self.logger.info(
                        "Uploaded %(filename)s to %(bucket_name)s",
                        {"filename": filename, "bucket_name": self.s3_bucket_name},
                    )
                else:
                    self.logger.info(
                        "File %(filename)s with size %(size_on_disk)d already exists in s3 bucket",
                        {"filename": filename, "size_on_disk": size_on_disk},
                    )
            else:
                self.logger.debug(
                    "Skipping S3 upload since bucket name is not configured"
                )

        else:
            os.remove(filename)
            self.logger.info("Removed %s", filename)

    def check_image_file_on_s3(self, filename, expected_size):
        if self.s3_bucket_name:
            s3 = boto3.resource("s3")
            try:
                object_summary = s3.ObjectSummary(self.s3_bucket_name, filename)
                if object_summary.size == expected_size:
                    return True
                else:
                    return False
            except botocore.exceptions.ClientError:
                return False
        else:
            return False

    @staticmethod
    def get_item_image_files(item_url):
        # Retrieve the item.
        params = {"fo": "json"}
        item_call = requests.get(item_url, params)
        item_result = item_call.json()
        image_resources = item_result.get("resources")[0]
        image_files = image_resources.get("files")
        return image_files

    def get_item_images(self, item_id):

        self.collection_data[item_id] = {}

        # Create an item ID folder and save all the files for the item
        destination_path = os.path.join(self.images_folder, item_id)
        if not os.path.exists(destination_path):
            os.makedirs(destination_path)

        item_url = self.ITEM_URL_FORMAT.format(item_id)

        image_files = self.get_item_image_files(item_url)
        # save the number of files / assets for this item
        self.logger.info(
            "Item %(item_id)s has %(image_count)d images",
            {"item_id": item_id, "image_count": len(image_files)},
        )
        self.collection_data[item_id]["size"] = len(image_files)
        self.collection_data[item_id]["item_url"] = item_url
        self.collection_data[item_id]["image_sizes"] = {}
        self.collection_data[item_id]["image_urls"] = {}

        counter = 0
        # Loop through all images in this item and save them all to the folder
        for item_image in image_files:
            greatest_width = 0
            jpeg_image_url = ""
            asset_height = 0

            # Don't assume the biggest jpeg is any particular index in the list
            # Instead, search the list for the image with the jpeg mime type
            # and pick the one with the greatest width
            for asset_file in item_image:
                if asset_file.get("mimetype") == self.MIME_TYPE:
                    if asset_file.get("width") > greatest_width:
                        greatest_width = asset_file.get("width")
                        jpeg_image_url = asset_file.get("url")
                        asset_height = asset_file.get("height")

            self.collection_data[item_id]["image_urls"][counter] = jpeg_image_url
            self.collection_data[item_id]["image_sizes"][counter] = {}
            self.collection_data[item_id]["image_sizes"][counter][
                "width"
            ] = greatest_width
            self.collection_data[item_id]["image_sizes"][counter][
                "height"
            ] = asset_height

            # create a filename that's the image number
            filename = "{0}.jpg".format(counter)
            filename = os.path.join(destination_path, filename)
            self.write_image_file(jpeg_image_url, filename, item_id, counter)
            counter = counter + 1

        # check whether the folder contains the number of items it should
        actual_item_count = len(os.listdir(destination_path))
        if self.collection_data[item_id]["size"] != actual_item_count:
            self.logger.error(
                "Should have %(expected_count)d images for item %(item_id)s but "
                "instead have %(actual_count)d images",
                {
                    "expected_count": self.collection_data[item_id]["size"],
                    "item_id": item_id,
                    "actual_count": actual_item_count,
                },
            )

    def get_and_save_images(self, results_url):
        """
        Input: the url for the collection or results set
        e.g. https://www.loc.gov/collections/baseball-cards

        Page through the collection result set
        """
        params = {
            "fo": "json",
            "c": self.COLLECTION_PAGINATION,
            "at": "results,pagination",
        }
        call = requests.get(results_url, params=params)
        data = call.json()
        results = data["results"]
        for result in results:
            # Don't try to get images from the collection-level result or web page results
            if "collection" not in result.get(
                "original_format"
            ) and "web page" not in result.get("original_format"):

                # All results should have an ID and an image_url
                if result.get("image_url") and result.get("id"):
                    identifier = urlparse(result["id"])[2].rstrip("/")
                    identifier = identifier.split("/")[-1]
                    self.get_item_images(identifier)

        # Recurse through the next page
        if data["pagination"]["next"] is not None:
            next_url = data["pagination"]["next"]
            self.logger.info("Getting next page: %s", next_url)
            self.get_and_save_images(next_url)
