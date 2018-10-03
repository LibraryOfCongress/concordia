from django.core.files.base import ContentFile
import io
import os
import zipfile

from django.conf import settings
from django.test import TestCase
from django.core.files.storage import default_storage

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

        # create user and login
        self.user = User.objects.create(username="tester", email="tester@example.com")
        self.user.set_password("top_secret")
        self.user.save()

        self.client.login(username="tester", password="top_secret")

    def test_ExportCampaignToBagit_get(self):
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
            media_url="foo/1.jpg",
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

        response = self.client.get("/campaigns/exportBagit/%s/" % campaign.slug)

        self.assertEqual(response.status_code, 200)
        self.assertEquals(
            response.get("Content-Disposition"),
            "attachment; filename=%s.zip" % campaign.slug,
        )

        f = io.BytesIO(response.content)
        zipped_file = zipfile.ZipFile(f, "r")

        # self.assertIsNone(zipped_file.testzip())
        self.assertIn("bagit.txt", zipped_file.namelist())
        self.assertIn("bag-info.txt", zipped_file.namelist())
        self.assertIn("data/testasset/asset.txt", zipped_file.namelist())
