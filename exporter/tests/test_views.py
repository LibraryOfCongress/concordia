import io
import zipfile
from datetime import datetime

from django.test import TestCase
from django.urls import reverse

from concordia.models import MediaType, Transcription, User
from concordia.tests.utils import (
    create_asset,
    create_campaign,
    create_item,
    create_project,
)

DOWNLOAD_URL = (
    "http://tile.loc.gov/image-services/iiif/"
    "service:mss:mal:003:0036300:002/full/pct:25/0/default.jpg"
)

RESOURCE_URL = "https://www.loc.gov/resource/mal.0043300/"


class ViewTest_Exporter(TestCase):
    """
    This class contains the unit tests for the view in the exporter app.

    Make sure the postgresql db is available. Run docker-compose up db
    """

    def setUp(self):
        user = User.objects.create(
            username="tester", email="tester@example.com", is_staff=True
        )
        user.set_password("top_secret")
        user.save()

        self.assertTrue(
            self.client.login(username="tester", password="top_secret")  # nosec
        )

        campaign = create_campaign(published=True)
        project = create_project(campaign=campaign, published=True)
        item = create_item(project=project, published=True)

        asset = create_asset(
            item=item,
            title="TestAsset",
            description="Asset Description",
            download_url=DOWNLOAD_URL,
            resource_url=RESOURCE_URL,
            media_type=MediaType.IMAGE,
            sequence=1,
        )

        self.asset_id = asset.id

        # add a Transcription object
        transcription1 = Transcription(
            asset=asset,
            user=user,
            text="Sample",
            submitted=datetime.now(),
            accepted=datetime.now(),
        )
        transcription1.full_clean()
        transcription1.save()

    def test_csv_export(self):
        """
        Test Campaign export as CSV
        """

        campaign_slug = "test-campaign"

        response = self.client.get(
            reverse("transcriptions:campaign-export-csv", args=(campaign_slug,))
        )

        expected_response_content = (
            "b'Campaign,Project,Item,ItemId,Asset,AssetId,AssetStatus,"
            "DownloadUrl,Transcription,Tags\\r\\n'"
            "b'Test Campaign,Test Project,Test Item,"
            f"testitem.0123456789,TestAsset,{self.asset_id},completed,"
            "http://tile.loc.gov/image-services/"
            "iiif/service:mss:mal:003:0036300:002/full"
            "/pct:25/0/default.jpg,Sample,\\r\\n'"
        )

        self.assertEqual(response.status_code, 200)
        response_content = "".join(map(str, response.streaming_content))

        self.assertEqual(response_content, expected_response_content)

    def test_bagit_export(self):
        """
        Test Campaign export as Bagit
        """

        campaign_slug = "test-campaign"

        response = self.client.get(
            reverse("transcriptions:campaign-export-bagit", args=(campaign_slug,))
        )

        self.assertEqual(response.status_code, 200)

        export_filename = "%s.zip" % (campaign_slug,)
        self.assertEquals(
            response.get("Content-Disposition"),
            "attachment; filename=%s" % export_filename,
        )

        f = io.BytesIO(response.content)
        zipped_file = zipfile.ZipFile(f, "r")

        self.assertIn("bagit.txt", zipped_file.namelist())
        self.assertIn("bag-info.txt", zipped_file.namelist())
        self.assertIn("data/mss/mal/003/0036300/002.txt", zipped_file.namelist())
