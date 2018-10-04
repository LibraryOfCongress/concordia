import io
import os
import zipfile

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase
from django.urls import reverse

from concordia.models import MediaType, Status, Transcription, User
from concordia.tests.utils import (
    create_asset,
    create_campaign,
    create_item,
    create_project,
)


class ViewTest_Exporter(TestCase):
    """
    This class contains the unit tests for the view in the exporter app.

    Make sure the postgresql db is available. Run docker-compose up db
    """

    def login_user(self):
        """
        Create a user and log the user in
        """

        self.user = User.objects.create(username="tester", email="tester@example.com")
        self.user.set_password("top_secret")
        self.user.save()

        self.assertTrue(self.client.login(username="tester", password="top_secret"))

    def test_csv_export(self):
        """
        Test GET route /campaigns/export/<slug-value>/ (campaign)
        """
        self.login_user()

        asset = create_asset()

        response = self.client.get(
            reverse(
                "transcriptions:export-csv", args=(asset.item.project.campaign.slug,)
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.content.decode("utf-8"),
            "Campaign,Title,Description,MediaUrl,Transcription,Tags\r\n"
            "Test Campaign,Test Asset,,1.jpg,,\r\n",
        )

    def test_bagit_export(self):
        """
        Test the http GET on route /campaigns/exportBagit/<campaignname>/
        """

        self.login_user()

        campaign = create_campaign(status=Status.EDIT, published=True)
        project = create_project(campaign=campaign, published=True)
        item = create_item(project=project, published=True)

        asset = create_asset(
            item=item,
            title="TestAsset",
            description="Asset Description",
            media_url="1.jpg",
            media_type=MediaType.IMAGE,
            sequence=1,
            status=Status.EDIT,
        )

        # add a Transcription object
        transcription1 = Transcription(
            asset=asset, user=self.user, status=Status.EDIT, text="Sample"
        )
        transcription1.full_clean()
        transcription1.save()

        item_dir = os.path.join(
            settings.MEDIA_ROOT, campaign.slug, project.slug, item.item_id, asset.slug
        )

        asset_file = ContentFile(b"Not a real JPEG")
        default_storage.save(
            os.path.join(item_dir, f"{asset.sequence}.jpg"), asset_file
        )

        response = self.client.get(
            reverse("transcriptions:export-bagit", args=(campaign.slug,))
        )

        self.assertEqual(response.status_code, 200)
        self.assertEquals(
            response.get("Content-Disposition"),
            "attachment; filename=%s.zip" % campaign.slug,
        )

        f = io.BytesIO(response.content)
        zipped_file = zipfile.ZipFile(f, "r")

        self.assertIn("bagit.txt", zipped_file.namelist())
        self.assertIn("bag-info.txt", zipped_file.namelist())
        self.assertIn(
            "data/test-project/testitem0123456789/testasset/1.jpg",
            zipped_file.namelist(),
        )
