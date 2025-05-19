import io
import tempfile
import zipfile
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from concordia.models import Asset, MediaType, Transcription, User
from concordia.tests.utils import (
    create_asset,
    create_campaign,
    create_item,
    create_project,
)
from exporter.views import (
    ExportProjectToCSV,
    do_bagit_export,
    get_latest_transcription_data,
    get_original_asset_id,
    write_distinct_asset_resource_file,
)

DOWNLOAD_URL = (
    "http://tile.loc.gov/image-services/iiif/"
    "service:mss:mal:003:0036300:002/full/pct:25/0/default.jpg"
)

RESOURCE_URL = "https://www.loc.gov/resource/mal.0043300/"


class ViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            username="tester", email="tester@example.com", is_staff=True
        )
        self.user.set_password("top_secret")
        self.user.save()
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

        transcription = Transcription(
            asset=self.asset,
            user=self.user,
            text="Sample",
            submitted=timezone.now(),
            accepted=timezone.now(),
        )
        transcription.full_clean()
        transcription.save()

        # Create another project with the same slug in a different campaign
        # to ensure this does not cause issues with any exports
        campaign2 = create_campaign(published=True, slug="test-campaign-2")
        create_project(campaign=campaign2, published=True, slug=self.project.slug)

    def test_csv_export(self):
        response = self.client.get(
            reverse("transcriptions:campaign-export-csv", args=(self.campaign.slug,))
        )
        self.assertEqual(response.status_code, 200)
        response_content = "".join(map(str, response.streaming_content))
        self.assertIn(
            "Campaign,Project,Item,ItemId,Asset,AssetId,AssetStatus", response_content
        )
        self.assertIn("TestAsset", response_content)
        self.assertIn("Sample", response_content)

    def test_campaign_bagit_export(self):
        response = self.client.get(
            reverse("transcriptions:campaign-export-bagit", args=(self.campaign.slug,))
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Content-Disposition", response)

        f = io.BytesIO(response.content)
        zipped = zipfile.ZipFile(f, "r")
        self.assertIn("bagit.txt", zipped.namelist())
        self.assertIn("data/mss/mal/003/0036300/002.txt", zipped.namelist())

    def test_project_bagit_export(self):
        response = self.client.get(
            reverse(
                "transcriptions:project-export-bagit",
                args=(self.campaign.slug, self.project.slug),
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Content-Disposition", response)

        f = io.BytesIO(response.content)
        zipped = zipfile.ZipFile(f, "r")
        self.assertIn("bagit.txt", zipped.namelist())
        self.assertIn("data/mss/mal/003/0036300/002.txt", zipped.namelist())

    def test_project_csv_export(self):
        # We test this view directly because it's not accessible except
        # through the admin, and so is not in urls.py
        request = self.client.get("/").wsgi_request
        request.user = self.user
        request.user.is_staff = True

        response = ExportProjectToCSV.as_view()(
            request, campaign_slug=self.campaign.slug, project_slug=self.project.slug
        )

        self.assertEqual(response.status_code, 200)
        response_content = b"".join(response.streaming_content).decode()
        self.assertIn("TestAsset", response_content)
        self.assertIn("Sample", response_content)

    def test_item_bagit_export(self):
        response = self.client.get(
            reverse(
                "transcriptions:item-export-bagit",
                args=(self.campaign.slug, self.project.slug, self.item.item_id),
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Content-Disposition", response)
        f = io.BytesIO(response.content)
        zipped = zipfile.ZipFile(f, "r")
        self.assertIn("bagit.txt", zipped.namelist())
        self.assertIn("data/mss/mal/003/0036300/002.txt", zipped.namelist())

    def test_get_original_asset_id_fallback(self):
        fallback_url = "http://example.com/image.jpg"
        self.assertEqual(get_original_asset_id(fallback_url), fallback_url)

    def test_get_original_asset_id_failure(self):
        invalid_url = "http://tile.loc.gov/image-services/iiif/master/no/match/here"
        with self.assertRaises(ValueError):
            get_original_asset_id(invalid_url)

    def test_write_distinct_asset_resource_file_missing_url(self):
        self.asset.resource_url = ""
        self.asset.save()

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(AssertionError):
                write_distinct_asset_resource_file([self.asset.pk], tmpdir)

    @override_settings(EXPORT_S3_BUCKET_NAME=None)
    @patch("exporter.views.logger")
    def test_do_bagit_export_no_s3(self, mock_logger):
        assets = get_latest_transcription_data(Asset.objects.filter(pk=self.asset.pk))

        with tempfile.TemporaryDirectory() as tmpdir:
            response = do_bagit_export(assets, tmpdir, "sample-bagit")
            self.assertEqual(response.status_code, 200)
            self.assertIn("application/zip", response["Content-Type"])
