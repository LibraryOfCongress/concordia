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

        # Arrange
        self.login_user()

        ## Build test data for local storage collection ##
        # Collection Info (local storage)
        locstor_media_url_str = "/locstorcollection/testasset/asset.jpg"
        locstor_collection_name_str = "locstorcollection"
        locstor_asset_folder_name_str = "testasset"
        locstor_asset_name_str = "asset.jpg"

        # create a collection (local Storage)
        self.collection1 = Collection(
            title="LocStorCollection",
            slug=locstor_collection_name_str,
            description="Collection Description",
            metadata={"key": "val1"},
            is_active=True,
            s3_storage=False,
            status=Status.EDIT,
        )
        self.collection1.save()

        # create an Asset (local Storage)
        self.asset1 = Asset(
            title="TestAsset",
            slug=locstor_asset_folder_name_str,
            description="Asset Description",
            media_url=locstor_media_url_str,
            media_type=MediaType.IMAGE,
            collection=self.collection1,
            sequence=0,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset1.save()

        # add a Transcription object
        self.transcription1 = Transcription(
            asset=self.asset1, user_id=self.user.id, status=Status.EDIT, text="Sample"
        )
        self.transcription1.save()

        ## Build test data for S3 Storage Collection ##
        # Collection Info (S3 storage)
        s3_media_url_str = "https://s3.us-east-2.amazonaws.com/chc-collections/test_s3/mss859430177/0.jpg"
        s3_collection_name_str = "test_s3"
        s3_asset_folder_name_str = "testasset"
        s3_asset_name_str = "asset.jpg"

        # create a collection (local Storage)
        self.collection2 = Collection(
            title="Test S3",
            slug=s3_collection_name_str,
            description="Collection Description",
            metadata={"key": "val1"},
            is_active=True,
            s3_storage=True,
            status=Status.EDIT,
        )
        self.collection2.save()

        # create an Asset (local Storage)
        self.asset2 = Asset(
            title="TestAsset",
            slug=s3_asset_folder_name_str,
            description="Asset Description",
            media_url=s3_media_url_str,
            media_type=MediaType.IMAGE,
            collection=self.collection2,
            sequence=0,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset2.save()

        # add a Transcription object
        self.transcription2 = Transcription(
            asset=self.asset2, user_id=self.user.id, status=Status.EDIT, text="Sample"
        )
        self.transcription2.save()


        # Make sure correct folders structure exists for Local Storage Collection
        collection_folder = "{0}/{1}".format(settings.MEDIA_ROOT, locstor_collection_name_str)
        if not os.path.exists(collection_folder):
            os.makedirs(collection_folder)
        item_dir = "{0}/{1}".format(collection_folder, locstor_asset_folder_name_str)
        if not os.path.exists(item_dir):
            os.makedirs(item_dir)

        # create source asset file for Local Storage Collection
        with open("{0}/{1}".format(item_dir, locstor_asset_name_str), "w+") as csv_file:
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

        # Act (local storage collection)
        response = self.client.get("/transcribe/exportBagit/locstorcollection/")

        # Assert for Local Storage Collection

        self.assertEqual(response.status_code, 200)
        self.assertEquals(
            response.get("Content-Disposition"),
            "attachment; filename=locstorcollection.zip",
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


        # Act (s3 collection)
        response2 = self.client.get("/transcribe/exportBagit/test_s3/")

        # Assert for s3 Collection

        self.assertEqual(response2.status_code, 200)
        self.assertEquals(
            response2.get("Content-Disposition"),
            "attachment; filename=test_s3.zip",
        )
        try:
            f = io.BytesIO(response2.content)
            zipped_file = zipfile.ZipFile(f, "r")

            self.assertIn("bagit.txt", zipped_file.namelist())
            self.assertIn("bag-info.txt", zipped_file.namelist())
            self.assertIn("data/mss859430177/0.txt", zipped_file.namelist())
            self.assertIn("data/mss859430177/0.jpg", zipped_file.namelist())

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
