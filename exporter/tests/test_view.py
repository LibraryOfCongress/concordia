# TODO: Add correct copyright header

import csv
import io
import os
import shutil
import sys
import zipfile

from django.conf import settings
from django.test import Client, TestCase

from concordia.models import (Asset, Collection, MediaType, Status,
                              Transcription, User)

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

        # login = self.client.login(username="tester", password="top_secret")

    def test_ExportCollectionToBagit_get(self):
        """
        Test the http GET on route /transcribe/exportBagit/<collectionname>/
        :return:
        """

        # Arrange
        self.login_user()

        # create a collection
        self.collection = Collection(
            title="FooCollection",
            slug="foocollection",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.PCT_0,
        )
        self.collection.save()

        # create an Asset
        self.asset = Asset(
            title="TestAsset",
            slug="testasset",
            description="Asset Description",
            media_url="/concordia/foocollection/testasset/asset.jpg",
            media_type=MediaType.IMAGE,
            collection=self.collection,
            metadata={"key": "val2"},
            status=Status.PCT_0,
        )
        self.asset.save()

        # add a Transcription object
        self.transcription = Transcription(
            asset=self.asset, user_id=self.user.id, status=Status.PCT_0, text="Sample"
        )
        self.transcription.save()

        # Make sure correct folders structure exists
        build_folder = "%s/concordia" % (settings.MEDIA_ROOT)
        if not os.path.exists(build_folder):
            os.makedirs(build_folder)
        collection_folder = build_folder + "/foocollection"
        if not os.path.exists(collection_folder):
            os.makedirs(collection_folder)
        asset_folder = collection_folder +"/testasset"
        if not os.path.exists(asset_folder):
            os.makedirs(asset_folder)

        source_dir = asset_folder

        # create source asset file
        with open(source_dir + "/asset.jpg", "w+") as csv_file:
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
            self.assertIn("data/testasset/export.csv", zipped_file.namelist())

            csv_file = zipped_file.read("data/testasset/export.csv")

            self.assertEqual(
                str(csv_file),
                "b'Collection,Title,Description,MediaUrl,Transcription,Tags\\r\\nFooCollection,TestAsset,Asset Description,/concordia/foocollection/testasset/asset.jpg,,\\r\\n'",  # noqa
            )
        finally:
            zipped_file.close()
            f.close()

        # Clean up temp folders
        try:
            shutil.rmtree(collection_folder)
        except:
            pass
