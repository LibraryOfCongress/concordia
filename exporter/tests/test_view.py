import csv
import io
import os
import shutil
import zipfile

import boto3
from django.conf import settings
from django.test import TestCase

from concordia.models import Asset, Campaign, MediaType, Status, Transcription, User


class ViewTest_Exporter(TestCase):
    """
    This class contains the unit tests for the view in the exporter app.

    Make sure the postgresql db is available. Run docker-compose up db
    """

    def login_user(self):
        """
        Create a user and log the user in
        """

        # create user and login
        self.user = User.objects.create(username="tester", email="tester@example.com")
        self.user.set_password("top_secret")
        self.user.save()

    def test_ExportCampaignToBagit_get(self):
        """
        Test the http GET on route /campaigns/exportBagit/<campaignname>/
        """

        self.login_user()

        # Build test data for local storage campaign #

        # Campaign Info (local storage)
        locstor_media_url_str = "/locstorcampaign/testasset/asset.jpg"
        locstor_campaign_name_str = "locstorcampaign"
        locstor_asset_folder_name_str = "testasset"
        locstor_asset_name_str = "asset.jpg"

        # create a campaign (local Storage)
        self.campaign1 = Campaign(
            title="LocStorCampaign",
            slug=locstor_campaign_name_str,
            description="Campaign Description",
            metadata={"key": "val1"},
            s3_storage=False,
            status=Status.EDIT,
        )
        self.campaign1.save()

        # create an Asset (local Storage)
        self.asset1 = Asset(
            title="TestAsset",
            slug=locstor_asset_folder_name_str,
            description="Asset Description",
            media_url=locstor_media_url_str,
            media_type=MediaType.IMAGE,
            campaign=self.campaign1,
            sequence=0,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset1.save()

        # add a Transcription object
        self.transcription1 = Transcription(
            asset=self.asset1, user=self.user, status=Status.EDIT, text="Sample"
        )
        self.transcription1.save()

        # Build test data for S3 Storage Campaign #
        # Campaign Info (S3 storage)
        s3_media_url_str = "https://s3.us-east-2.amazonaws.com/chc-collections/test_s3/mss859430177/0.jpg"
        s3_campaign_name_str = "test_s3"
        s3_asset_folder_name_str = "testasset"
        s3_asset_name_str = "asset.jpg"

        # create a campaign (local Storage)
        self.campaign2 = Campaign(
            title="Test S3",
            slug=s3_campaign_name_str,
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign2.save()

        # create an Asset (local Storage)
        self.asset2 = Asset(
            title="TestAsset",
            slug=s3_asset_folder_name_str,
            description="Asset Description",
            media_url=s3_media_url_str,
            media_type=MediaType.IMAGE,
            campaign=self.campaign2,
            sequence=0,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset2.save()

        # add a Transcription object
        self.transcription2 = Transcription(
            asset=self.asset2, user=self.user, status=Status.EDIT, text="Sample"
        )
        self.transcription2.save()

        # Make sure correct folders structure exists for Local Storage Campaign
        campaign_folder = "{0}/{1}".format(
            settings.MEDIA_ROOT, locstor_campaign_name_str
        )
        if not os.path.exists(campaign_folder):
            os.makedirs(campaign_folder)
        item_dir = "{0}/{1}".format(campaign_folder, locstor_asset_folder_name_str)
        if not os.path.exists(item_dir):
            os.makedirs(item_dir)

        # create source asset file for Local Storage Campaign
        with open("{0}/{1}".format(item_dir, locstor_asset_name_str), "w+") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(
                [
                    "Campaign",
                    "Title",
                    "Description",
                    "MediaUrl",
                    "Transcription",
                    "Tags",
                ]
            )

        # Act (local storage campaign)
        response = self.client.get("/campaigns/exportBagit/locstorcampaign/")

        # Assert for Local Storage Campaign

        self.assertEqual(response.status_code, 200)
        self.assertEquals(
            response.get("Content-Disposition"),
            "attachment; filename=locstorcampaign.zip",
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

        # Act (s3 campaign)
        response2 = self.client.get("/campaigns/exportBagit/test_s3/")

        # Assert for s3 Campaign

        self.assertEqual(response2.status_code, 200)
        self.assertEquals(
            response2.get("Content-Disposition"), "attachment; filename=test_s3.zip"
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
            shutil.rmtree(campaign_folder)
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
