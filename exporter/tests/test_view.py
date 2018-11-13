import io
import zipfile

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


class ViewTest_Exporter(TestCase):
    """
    This class contains the unit tests for the view in the exporter app.

    Make sure the postgresql db is available. Run docker-compose up db
    """

    def setUp(self):
        user = User.objects.create(username="tester", email="tester@example.com")
        user.set_password("top_secret")
        user.save()

        self.assertTrue(self.client.login(username="tester", password="top_secret"))

        campaign = create_campaign(published=True)
        project = create_project(campaign=campaign, published=True)
        item = create_item(project=project, published=True)

        asset = create_asset(
            item=item,
            title="TestAsset",
            description="Asset Description",
            download_url=DOWNLOAD_URL,
            media_type=MediaType.IMAGE,
            sequence=1,
        )

        # add a Transcription object
        transcription1 = Transcription(asset=asset, user=user, text="Sample")
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
            "b'Campaign,Project,Item,ItemId,Asset,"
            "AssetStatus,DownloadUrl,Transcription\\r\\n'"
            "b'Test Campaign,Test Project,Test Item,"
            "testitem0123456789,TestAsset,edit,"
            "http://tile.loc.gov/image-services/"
            "iiif/service:mss:mal:003:0036300:002/full"
            "/pct:25/0/default.jpg,Sample\\r\\n'"
        )

        self.assertEqual(response.status_code, 200)
        response_content = "".join(map(str, response.streaming_content))
        self.assertEqual(response_content, expected_response_content)

    def test_bagit_export(self):
        """
        Test Campaign export as CSV
        """

        campaign_slug = "test-campaign"

        response = self.client.get(
            reverse("transcriptions:campaign-export-bagit", args=(campaign_slug,))
        )

        self.assertEqual(response.status_code, 200)
        self.assertEquals(
            response.get("Content-Disposition"),
            "attachment; filename=%s.zip" % campaign_slug,
        )

        f = io.BytesIO(response.content)
        zipped_file = zipfile.ZipFile(f, "r")

        self.assertIn("bagit.txt", zipped_file.namelist())
        self.assertIn("bag-info.txt", zipped_file.namelist())
        self.assertIn(
            "data/test-project/testitem0123456789/mss-mal-003-0036300-002.txt",
            zipped_file.namelist(),
        )
