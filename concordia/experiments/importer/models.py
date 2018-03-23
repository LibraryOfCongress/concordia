from __future__ import absolute_import, unicode_literals
import requests
import os
from urllib.parse import urlparse
import boto3
import botocore
from PIL import Image
import logging
from config import config



class Importer:
    # Config loaded from Django settings
    base_url = ''
    item_count = 0
    images_folder = ''
    s3_bucket_name = ''

    # Constants
    MIME_TYPE = "image/jpeg"
    COLLECTION_PAGINATION = 25
    IMAGE_CHUNK_SIZE = 100000
    ITEM_URL_FORMAT = "https://dev.loc.gov/item/{0}"

    # Ephemeral data
    collection_data = {}

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        self.base_url = config('IMPORTER', 'BASE_URL')
        self.item_count = config('IMPORTER', 'ITEM_COUNT')
        self.images_folder = config('IMPORTER', 'IMAGES_FOLDER')
        self.s3_bucket_name = config('IMPORTER', 'S3_BUCKET_NAME')

    def main(self):

        self.get_and_save_images(self.base_url)
        self.check_total_item_count()

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

    def check_total_item_count(self):
        # Check that the total number of items matches the expected configured number of total items
        actual_item_count = os.listdir(self.images_folder)

        if actual_item_count != self.item_count:
            self.logger.error("Expected item count {0} but actual item count of {1} is {2}".format(
                self.item_count,
                self.images_folder,
                actual_item_count
            ))
            return False
        else:
            return True

    def check_item_folder_completeness(self, item_id):
        item_url = self.ITEM_URL_FORMAT.format(item_id)
        image_files = self.get_item_image_files(item_url)
        expected_image_count = len(image_files)
        actual_image_count = len(os.listdir(os.path.join(self.images_folder, item_id)))
        if expected_image_count != actual_image_count:
            self.logger.error("Item {0} is expected to have {1} images "
                              "but actually has {2} images".format(item_id,
                                                                   expected_image_count,
                                                                   actual_image_count))
            return False
        else:
            self.logger.info("Item {0} has the expected number of {1} images".format(item_id, actual_image_count))
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
            self.logger.info("Actual width and height of {0} are {1} and {2} respectively".format(
                filename,
                actual_width,
                actual_height
            ))

            image_file.verify()
            self.logger.info("Completed verification of {0}".format(filename))

            # check image width and height and verify that it matches the expected sizes
            expected_width = self.collection_data[identifier]["image_sizes"][image_number]["width"]
            expected_height = self.collection_data[identifier]["image_sizes"][image_number]["height"]
            self.logger.info("Expected width and height of {0} are {1} and {2} respectively".format(
                filename,
                expected_width,
                expected_height
            ))

            if actual_width != expected_width and abs(actual_width-expected_width) > 1:
                self.logger.error(
                    "Expected width of {0} but actual image width is {1}".format(expected_width, actual_width))
                return False

            if actual_height != expected_height and abs(actual_width-expected_width) > 1:
                self.logger.error("Expected height of {0} but actual image height is {1}".format(expected_height,
                                                                                                 actual_height))
                return False
        except IOError:
            self.logger.error("An exception occurred attempting to verify {0}".format(filename))
            return False

        return True

    def write_image_file(self, image, filename, identifier, image_number):
        # Check if we already have this image on disk
        if not self.check_item_image_exists(filename):
            # Request the image and write it to filename

            self.logger.info("Requesting {0}".format(image.replace("tile.loc.gov","tile-dev.loc.gov")))
            image_response = requests.get(image.replace("tile.loc.gov","tile-dev.loc.gov"), stream=True)
            with open(filename, 'wb') as fd:
                for chunk in image_response.iter_content(chunk_size=self.IMAGE_CHUNK_SIZE):
                    fd.write(chunk)
                    self.logger.debug("Writing another {0} size chunk".format(self.IMAGE_CHUNK_SIZE))

            self.logger.info("Finished writing the image file {0}".format(filename))

        # If the image successfully verifies, upload it to the S3 bucket
        if self.verify_item_image(filename, identifier, image_number):
            image_stats = os.stat(filename)
            size_on_disk = image_stats.st_size
            if not self.check_image_file_on_s3(filename, size_on_disk):
                s3 = boto3.client('s3')
                # TODO: If the s3 bucket doesn't exist yet, try to create it
                # TODO: Queue the S3 uploads so they can occur asynchronously (simultaneously with loc.gov downloads)
                s3.upload_file(filename, self.s3_bucket_name, filename)
                self.logger.info("Uploaded {0} to {1}".format(filename, self.s3_bucket_name))
            else:
                self.logger.info("File {0} with size {1} already exists in s3 bucket".format(
                    filename,
                    size_on_disk
                ))
        else:
            os.remove(filename)
            self.logger.info("Removed {0}".format(filename))

    def check_image_file_on_s3(self, filename, expected_size):
        s3 = boto3.resource('s3')
        try:
            object_summary = s3.ObjectSummary(self.s3_bucket_name, filename)
            if object_summary.size == expected_size:
                return True
            else:
                return False
        except botocore.exceptions.ClientError:
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

    def get_item_images(self, item_id, item_url, path):
        image_files = self.get_item_image_files(item_url)
        # save the number of files / assets for this item
        self.logger.info("Item {0} has {1} images".format(item_id, len(image_files)))
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
            self.collection_data[item_id]["image_sizes"][counter]["width"] = greatest_width
            self.collection_data[item_id]["image_sizes"][counter]["height"] = asset_height

            # create a filename that's the image number
            filename = "{0}.jpg".format(counter)
            filename = os.path.join(path, filename)
            self.write_image_file(jpeg_image_url, filename, item_id, counter)
            counter = counter + 1

    def get_and_save_images(self, results_url):
        """
        Input: the url for the collection or results set
        e.g. https://www.loc.gov/collections/baseball-cards

        Page through the collection result set
        """
        params = {"fo": "json", "c": self.COLLECTION_PAGINATION, "at": "results,pagination"}
        call = requests.get(results_url, params=params)
        data = call.json()
        results = data['results']
        for result in results:
            # Don't try to get images from the collection-level result or web page results
            if "collection" not in result.get("original_format") \
                    and "web page" not in result.get("original_format"):

                # All results should have an ID and an image_url
                if result.get("image_url") and result.get("id"):
                    identifier = urlparse(result["id"])[2].rstrip('/')
                    identifier = identifier.split('/')[-1]

                    self.collection_data[identifier] = {}

                    # Create an item ID folder and save all the files for the item
                    destination_folder = os.path.join(self.images_folder, identifier)
                    if not os.path.exists(destination_folder):
                        os.makedirs(destination_folder)
                    self.get_item_images(identifier, result.get("id"), destination_folder)

                    # check whether the folder contains the number of items it should
                    actual_item_count = len(os.listdir(destination_folder))
                    if self.collection_data[identifier]["size"] != actual_item_count:
                        self.logger.error("Should have {0} images for item {1} but instead have {2} images".format(
                            self.collection_data[identifier]["size"],
                            identifier,
                            actual_item_count
                        ))

        # Recurse through the next page
        if data["pagination"]["next"] is not None:
            next_url = data["pagination"]["next"]
            self.logger.info("Getting next page: {0}".format(next_url))
            self.get_and_save_images(next_url)
