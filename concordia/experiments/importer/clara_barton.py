import requests
import os
from urllib.parse import urlparse
import boto3
from PIL import Image

base_url = 'https://www.loc.gov/collections/clara-barton-papers'
images_folder = 'clara-barton-papers'
s3_bucket_name = 'clara-barton-papers'
item_count = 933
JPEG_MIME_TYPE = "image/jpeg"
collection_data = {}


def write_image_file(image, filename):
    # Request the image and write it to filename
    image_response = requests.get(image, stream=True)
    with open(filename, 'wb') as fd:
        for chunk in image_response.iter_content(chunk_size=100000):
            fd.write(chunk)

    # TODO: check the size of the downloaded file to make sure it matches
    # TODO: what was provided by the API

    # If the image was successfully downloaded, upload it to the S3 bucket
    try:
        image_file = Image.open(filename)
        image_file.verify()
        s3 = boto3.client('s3')
        s3.upload_file(filename, s3_bucket_name, filename)
    except IOError:
        print("An exception occurred attempting to verify {0}".format(filename))


def get_item_images(item_id, item_url, path):
    # Retrieve the item.
    params = {"fo": "json"}
    item_call = requests.get(item_url, params)
    item_result = item_call.json()
    image_files = item_result.get("resources")[0]

    # save the number of files / assets for this item
    collection_data[item_id]["size"] = len(image_files)
    collection_data[item_id]["item_url"] = item_url
    collection_data[item_id]["image_sizes"] = []
    collection_data[item_id]["image_urls"] = []

    counter = 0
    # Loop through all images in this item and save them all to the folder
    for item_image in image_files.get("files"):
        greatest_width = 0

        # Don't assume the biggest jpeg is any particular index in the list
        # Instead, search the list for the image with the jpeg mime type
        # and pick the one with the greatest width
        for asset_file in item_image:
            if asset_file.get("mimetype") == JPEG_MIME_TYPE:
                if asset_file.get("width") > greatest_width:
                    greatest_width = asset_file.get("width")
                    jpeg_image_url = asset_file.get("url")
                    asset_size = asset_file.get("size")

        collection_data[item_id]["image_urls"].append(jpeg_image_url)
        collection_data[item_id]["image_sizes"].append(asset_size)

        # create a filename that's the image number
        filename = "{0}.jpg".format(counter)
        filename = os.path.join(path, filename)
        write_image_file(jpeg_image_url, filename)
        counter = counter + 1


def get_and_save_images(results_url, path):
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

                collection_data[identifier] = {}

                # If hassegments is false, then there is only one image for this item
                if not result.get("hassegments") or result.get("hassegments") is False:
                    # TODO: make sure the widest JPEG available is the one being downloaded
                    # TODO: for these single-image items
                    image = "https:" + result.get("image_url")[-1]

                    collection_data[identifier]["size"] = 1
                    collection_data[identifier]["item_url"] = result.get("id")
                    collection_data[identifier]["image_urls"][0] = image
                    collection_data[identifier]["image_sizes"][0] = result.get("size")

                    # Create a filename that's the identifier portion of the item URL
                    filename = "{0}.jpg".format(identifier)
                    filename = os.path.join(path, filename)
                    if not os.path.exists(path):
                        os.makedirs(path)
                    write_image_file(image, filename)

                    # TODO: check that the file saved is the same size provided by the API
                else:
                    # Multiple images / assets / files belong to this item
                    # Create an item ID folder and save all the files
                    destination_folder = os.path.join(path, identifier)
                    if not os.path.exists(destination_folder):
                        os.makedirs(destination_folder)
                    get_item_images(identifier, result.get("id"), destination_folder)

                    # TODO: check whether the folder contains the number of items it should

    # Recurse through the next page
    if data["pagination"]["next"] is not None:
        next_url = data["pagination"]["next"]
        print("getting next page: {0}".format(next_url))
        get_and_save_images(next_url, path)


get_and_save_images(base_url, images_folder)

# TODO: check that the total number of items - both folders and single-image items in the main folder -
# TODO: matches the expected number of total items configured at the top
# TODO: Save collection_data somewhere so we know which URLs were used to retrieve these images?
