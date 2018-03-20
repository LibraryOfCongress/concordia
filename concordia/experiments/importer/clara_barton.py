import requests
import os
from urllib.parse import urlparse
import boto3

base_url = 'https://www.loc.gov/collections/clara-barton-papers'
images_folder = 'clara-barton-papers'
s3_bucket_name = 'clara-barton-papers'


def write_image_file(image, filename):
    # request the image and write to path
    image_response = requests.get(image, stream=True)
    with open(filename, 'wb') as fd:
        for chunk in image_response.iter_content(chunk_size=100000):
            fd.write(chunk)

    s3 = boto3.client('s3')
    s3.upload_file(filename, s3_bucket_name, filename)


def get_item_images(item_url, path):
    # Retrieve the item.
    params = {"fo": "json"}
    item_call = requests.get(item_url, params)
    item_result = item_call.json()
    image_files = item_result.get("resources")[0]

    # Loop through all images in this item and save them all to the folder
    counter = 1
    for item_image in image_files.get("files"):
        image = item_image[-2].get("url")

        # create a filename that's the image number
        filename = "{0}.jpg".format(counter)
        filename = os.path.join(path, filename)
        write_image_file(image, filename)
        counter = counter + 1


def get_and_save_images(results_url, path):
    """
    Takes as input the url for the collection or results set
    e.g. https://www.loc.gov/collections/baseball-cards
    and a list of items (used for pagination)
    """
    params = {"fo": "json", "c": 25, "at": "results,pagination"}
    call = requests.get(results_url, params=params)
    data = call.json()
    results = data['results']
    for result in results:
        # don't try to get images from the collection-level result or web page results
        if "collection" not in result.get("original_format") \
                and "web page" not in result.get("original_format"):

            if result.get("image_url") and result.get("id"):
                identifier = urlparse(result["id"])[2].rstrip('/')
                identifier = identifier.split('/')[-1]

                if not result.get("hassegments") or result.get("hassegments") is False:
                    image = "https:" + result.get("image_url")[-1]
                    # create a filename that's the identifier portion of the item URL
                    filename = "{0}.jpg".format(identifier)
                    filename = os.path.join(path, filename)

                    write_image_file(image, filename)
                else:
                    dest_folder = os.path.join(path, identifier)
                    if not os.path.exists(dest_folder):
                        os.makedirs(dest_folder)
                    get_item_images(result.get("id"), dest_folder)

    if data["pagination"]["next"] is not None:  # make sure we haven't hit the end of the pages
        next_url = data["pagination"]["next"]
        print("getting next page: {0}".format(next_url))
        get_and_save_images(next_url, path)


get_and_save_images(base_url, images_folder)
