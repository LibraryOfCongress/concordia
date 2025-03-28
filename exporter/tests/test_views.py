import io
import zipfile

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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


class ViewTests(TestCase):
    """
    This class contains the unit tests for the views in the exporter app.
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

        self.campaign = create_campaign(published=True)
        self.project = create_project(campaign=self.campaign, published=True)
        self.item = create_item(project=self.project, published=True)

        self.asset = create_asset(
            item=self.item,
            title="TestAsset",
            description="Asset Description",
            download_url=DOWNLOAD_URL,
            resource_url=RESOURCE_URL,
            media_type=MediaType.IMAGE,
            sequence=1,
        )

        self.asset_id = self.asset.id

        # add a Transcription object
        transcription1 = Transcription(
            asset=self.asset,
            user=user,
            text="Sample",
            submitted=timezone.now(),
            accepted=timezone.now(),
        )
        transcription1.full_clean()
        transcription1.save()

        # Create another project with the same slug in a different campaign
        # to ensure this does not cause issues with any exports
        campaign2 = create_campaign(published=True, slug="test-campaign-2")
        create_project(campaign=campaign2, published=True, slug=self.project.slug)

    def test_csv_export(self):
        """
        Test Campaign export as CSV
        """

        campaign_slug = self.campaign.slug

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

    def test_campaign_bagit_export(self):
        """
        Test Campaign export as Bagit
        """

        campaign_slug = self.campaign.slug

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

    def test_project_bagit_export(self):
        """
        Test Project export as Bagit
        """

        campaign_slug = self.campaign.slug
        project_slug = self.project.slug

        response = self.client.get(
            reverse(
                "transcriptions:project-export-bagit",
                args=(campaign_slug, project_slug),
            )
        )

        self.assertEqual(response.status_code, 200)

        export_filename = "%s-%s.zip" % (campaign_slug, project_slug)
        self.assertEquals(
            response.get("Content-Disposition"),
            "attachment; filename=%s" % export_filename,
        )

        f = io.BytesIO(response.content)
        zipped_file = zipfile.ZipFile(f, "r")

        self.assertIn("bagit.txt", zipped_file.namelist())
        self.assertIn("bag-info.txt", zipped_file.namelist())
        self.assertIn("data/mss/mal/003/0036300/002.txt", zipped_file.namelist())
