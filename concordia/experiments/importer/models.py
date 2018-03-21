from __future__ import absolute_import, unicode_literals
from django.db import models
import requests
import os
from urllib.parse import urlparse
import boto3
from PIL import Image
import logging
import configparser
import sys


class Importer:
    base_url = ''
    item_count = 0
    images_folder = ''
    s3_bucket_name = ''

    JPEG_MIME_TYPE = "image/jpeg"
    collection_data = {}

    def __init__(self):
        logging.basicConfig(filename='importer.log', level=logging.INFO)

        config = configparser.ConfigParser()
        config.read(sys.argv[1])

        self.base_url = config['Collection']['base_url']
        self.item_count = config['Collection']['item_count']
        self.images_folder = config['Collection']['images_folder']
        self.s3_bucket_name = config['Collection']['s3_bucket_name']

    def main(self):

        self.get_and_save_images(self.base_url, self.images_folder)

        # check that the total number of items - both folders and single-image items in the main folder -
        # matches the expected number of total items configured at the top
        actual_item_count = os.listdir(self.images_folder)

        if actual_item_count != self.item_count:
            logging.error("Expected item count {0} but actual item count of {1} is {2}".format(
                self.item_count,
                self.images_folder,
                actual_item_count
            ))

    def write_image_file(self, image, filename, identifier, image_number):
        # Request the image and write it to filename
        image_response = requests.get(image, stream=True)
        with open(filename, 'wb') as fd:
            for chunk in image_response.iter_content(chunk_size=100000):
                fd.write(chunk)

        # If the image successfully verifies with Pillow, upload it to the S3 bucket
        try:
            image_file = Image.open(filename)
            actual_width, actual_height = image_file.size
            image_file.verify()
            image_file.close()

            # check image width and height and verify that it matches the expected sizes
            expected_width = self.collection_data[identifier]["image_sizes"][image_number]["width"]
            expected_height = self.collection_data[identifier]["image_sizes"][image_number]["height"]

            if actual_width != expected_width:
                logging.error(
                    "Expected width of {0} but actual image width is {1}".format(expected_width, actual_width))

            if actual_height != expected_height:
                logging.error("Expected height of {0} but actual image height is {1}".format(expected_height,
                                                                                             actual_height))

            s3 = boto3.client('s3')
            s3.upload_file(filename, self.s3_bucket_name, filename)
        except IOError:
            logging.error("An exception occurred attempting to verify {0}".format(filename))
            # TODO: clean up the bad file and retry download

    def get_item_images(self, item_id, item_url, path):
        # Retrieve the item.
        params = {"fo": "json"}
        item_call = requests.get(item_url, params)
        item_result = item_call.json()
        image_resources = item_result.get("resources")[0]
        image_files = image_resources.get("files")
        # save the number of files / assets for this item

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
                if asset_file.get("mimetype") == self.JPEG_MIME_TYPE:
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

    def get_and_save_images(self, results_url, path):
        """
        Takes as input the url for the collection or results set
        e.g. https://www.loc.gov/collections/baseball-cards
        and a path to a local folder (used for saving the downloaded images)
        """
        params = {"fo": "json", "c": 25, "at": "results,pagination"}
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

                    # Create an item ID folder and save all the files - whether one or many
                    destination_folder = os.path.join(path, identifier)
                    if not os.path.exists(destination_folder):
                        os.makedirs(destination_folder)
                    self.get_item_images(identifier, result.get("id"), destination_folder)

                    # check whether the folder contains the number of items it should
                    if self.collection_data[identifier]["size"] != len(os.listdir(destination_folder)):
                        logging.error("Should have {0} images for item {1} but instead have {2} images".format(
                            self.collection_data[identifier]["size"],
                            identifier,
                            len(os.listdir(destination_folder))
                        ))

        # Recurse through the next page
        if data["pagination"]["next"] is not None:
            next_url = data["pagination"]["next"]
            logging.info("getting next page: {0}".format(next_url))
            self.get_and_save_images(next_url, path)