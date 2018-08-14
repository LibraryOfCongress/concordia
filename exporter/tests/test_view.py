import csv
import io
import os
import shutil
import sys
import zipfile

import boto3
from django.conf import settings
from django.test import Client, TestCase

from concordia.models import Asset, Collection, MediaType, Status, Transcription, User

PACKAGE_PARENT = ".."
SCRIPT_DIR = os.path.dirname(
    os.path.realpath(os.path.join(os.getcwd(), os.path.expanduser(__file__)))
)
sys.path.append(os.path.normpath(os.path.join(SCRIPT_DIR, PACKAGE_PARENT)))
sys.path.append(os.path.join(SCRIPT_DIR, "../"))
sys.path.append(os.path.join(SCRIPT_DIR, "../../config"))


class ViewTest_Exporter(TestCase):
    """
    This class contains the unit tests for the view in the exporter app.

    Make sure the postgresql db is available. Run docker-compose up db
    """

    def setUp(self):
        """
        setUp is called before the execution of each test below
        :return:
        """

        self.client = Client()

    def login_user(self):
        """
        Create a user and log the user in
        :return:
        """
        # create user and login
        self.user = User.objects.create(username="tester", email="tester@foo.com")
        self.user.set_password("top_secret")
        self.user.save()

    def test_ExportCollectionToBagit_get(self):
        """
        Test the http GET on route /transcribe/exportBagit/<collectionname>/
        :return:
        """

        media_url_str = "/foocollection/testasset/asset.jpg"
        collection_name_str = "foocollection"
        asset_folder_name_str = "testasset"
        asset_name_str = "asset.jpg"

        # Arrange
        self.login_user()

        # create a collection
        self.collection = Collection(
            title="FooCollection",
            slug=collection_name_str,
            description="Collection Description",
            metadata={"key": "val1"},
            is_active=True,
            s3_storage=False,
            status=Status.EDIT,
        )
        self.collection.save()

        # create an Asset
        self.asset = Asset(
            title="TestAsset",
            slug=asset_folder_name_str,
            description="Asset Description",
            media_url=media_url_str,
            media_type=MediaType.IMAGE,
            collection=self.collection,
            sequence=0,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        # add a Transcription object
        self.transcription = Transcription(
            asset=self.asset, user_id=self.user.id, status=Status.EDIT, text="Sample"
        )
        self.transcription.save()

        # Make sure correct folders structure exists
        collection_folder = "{0}/{1}".format(settings.MEDIA_ROOT, collection_name_str)
        if not os.path.exists(collection_folder):
            os.makedirs(collection_folder)
        source_dir = "{0}/{1}".format(collection_folder, asset_folder_name_str)
        if not os.path.exists(source_dir):
            os.makedirs(source_dir)

        # create source asset file
        with open("{0}/{1}".format(source_dir, asset_name_str), "w+") as csv_file:
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

        # Act
        response = self.client.get("/transcribe/exportBagit/foocollection/")

        # Assert

        self.assertEqual(response.status_code, 200)
        self.assertEquals(
            response.get("Content-Disposition"),
            "attachment; filename=foocollection.zip",
        )
        try:
            f = io.BytesIO(response.content)
            zipped_file = zipfile.ZipFile(f, "r")

            # self.assertIsNone(zipped_file.testzip())
            self.assertIn("bagit.txt", zipped_file.namelist())
            self.assertIn("bag-info.txt", zipped_file.namelist())
            self.assertIn("data/testasset/asset.txt", zipped_file.namelist())

        finally:
            zipped_file.close()
            f.close()

        # Clean up temp folders
        try:
            shutil.rmtree(collection_folder)
        except Exception as e:
            pass


class AWS_S3_ConnectionTest(TestCase):
    """
    This class contains the test for the AWS S3 Connection
    """
    def test_connection(self):
        connection = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_S3["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=settings.AWS_S3["AWS_SECRET_ACCESS_KEY"],
        )
        self.assertIsNotNone(connection)
