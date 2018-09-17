# TODO: Add correct copyright header

import json
import logging
import time
from datetime import datetime, timedelta

from django.test import Client, TestCase
from django.utils.encoding import force_text
from rest_framework import status

from concordia.models import (
    Asset,
    Campaign,
    Item,
    MediaType,
    PageInUse,
    Project,
    Status,
    Tag,
    Transcription,
    User,
    UserProfile,
    UserAssetTagCollection,
)

logging.disable(logging.CRITICAL)


class ViewWSTest_Concordia(TestCase):
    """
    This class contains the unit tests for the view_ws in the concordia app.

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

        self.client.login(username="tester", password="top_secret")

        # create a session cookie
        self.client.session["foo"] = 123  # HACK: needed for django Client

    def test_AnonymousUser_get(self):
        """
        This unit test tests the get  route ws/anonymous_user/
        :param self:
        :return:
        """

        # Arrange
        self.login_user()

        # Act
        response = self.client.get("/ws/anonymous_user/")
        response2 = self.client.get("/ws/anonymous_user/")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.content, response2.content)

    def test_UserProfile_get(self):
        """
        This unit test tests the get route ws/user_profile/<user_id>/
        :param self:
        :return:
        """

        # Arrange
        self.login_user()

        profile = UserProfile(user_id=self.user.id)
        profile.save()

        # Act
        response = self.client.get("/ws/user_profile/%s/" % self.user.id)

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_PageInUse_post(self):
        """
        This unit test tests the post entry for the route ws/page_in_use
        :param self:
        :return:
        """

        # Arrange
        self.login_user()

        # Act
        response = self.client.post(
            "/ws/page_in_use/",
            {
                "page_url": "campaigns/American-Jerusalem/asset/mamcol.0930/",
                "user": self.user.id,
                "updated_on": datetime.now(),
            },
        )

        # Assert
        self.assert_post_successful(response)

    def test_PageInUse_delete_old_entries_post(self):
        """
        This unit test tests the post entry for the route ws/page_in_use
        the database has two items added the created_on timestamp of now - 10 minutes
        :param self:
        :return:
        """

        # Arrange
        self.login_user()

        time_threshold = datetime.now() - timedelta(minutes=10)
        page1 = PageInUse(
            page_url="foo.com/blah",
            user=self.user,
            created_on=time_threshold,
            updated_on=time_threshold,
        )
        page1.save()

        page2 = PageInUse(
            page_url="bar.com/blah",
            user=self.user,
            created_on=time_threshold,
            updated_on=time_threshold,
        )
        page2.save()

        # Act
        response = self.client.post(
            "/ws/page_in_use/",
            {
                "page_url": "campaigns/American-Jerusalem/asset/mamcol.0930/",
                "user": self.user.id,
                "updated_on": datetime.now(),
            },
        )

        # Assert
        self.assert_post_successful(response)

    def test_PageInUse_nologin_post(self):
        """
        This unit test tests the post entry for the route ws/page_in_use without logging in
        :param self:
        :return:
        """

        # Arrange
        # create user
        self.user = User.objects.create(username="foo", email="tester@foo.com")
        self.user.set_password("top_secret")
        self.user.save()

        # Act
        response = self.client.post(
            "/ws/page_in_use/",
            {
                "page_url": "campaigns/American-Jerusalem/asset/mamcol.0930/",
                "user": self.user.id,
            },
        )

        # Assert
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # Verify the entry is not in the PagInUse table
        page_in_use = PageInUse.objects.all()
        self.assertEqual(len(page_in_use), 0)

    def test_PageInUse_nologin_anonymous_post(self):
        """
        This unit test tests the post entry for the route ws/page_in_use without logging
        and the user is anonymous
        :param self:
        :return:
        """

        # Arrange
        # create user
        self.user = User.objects.create(username="anonymous", email="tester@foo.com")
        self.user.set_password("top_secret")
        self.user.save()

        # Act
        response = self.client.post(
            "/ws/page_in_use/",
            {
                "page_url": "campaigns/American-Jerusalem/asset/mamcol.0930/",
                "user": self.user.id,
                "updated_on": datetime.now(),
            },
        )

        # Assert
        self.assert_post_successful(response)

    def assert_post_successful(self, response):
        """
        Check the results of a successful post and insert of a PageInUse database item
        :param response:
        :return:
        """
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify the entry is in the PagInUse table
        page_in_use = PageInUse.objects.all()
        self.assertEqual(len(page_in_use), 1)

    def test_PageInUse_get(self):
        """
        This unit test tests the get entry for the route ws/page_in_use/url
        :param self:
        :return:
        """

        # Arrange
        self.login_user()

        # Add two values to database
        PageInUse.objects.create(page_url="foo.com/blah", user=self.user)

        page_in_use = PageInUse.objects.create(page_url="bar.com/blah", user=self.user)

        # Act
        response = self.client.get("/ws/page_in_use/bar.com/blah/")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertJSONEqual(
            str(response.content, encoding="utf8"),
            {
                "page_url": "bar.com/blah",
                "user": self.user.id,
                "updated_on": page_in_use.updated_on.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            },
        )

    def test_PageInUseUser_get(self):
        """
        This unit test tests the get entry for the route ws/page_in_use_user/user/url/
        :param self:
        :return:
        """

        # Arrange
        self.login_user()

        # create second user
        self.user2 = User.objects.create(username="bar", email="tester2@foo.com")
        self.user2.set_password("top_secret")
        self.user2.save()

        test_page_url = "foo.com/blah"
        # Add two values to database
        page_in_use = PageInUse.objects.create(page_url=test_page_url, user=self.user)

        PageInUse.objects.create(page_url="bar.com/blah", user=self.user2)

        # Act
        response = self.client.get(
            "/ws/page_in_use_user/%s/%s/" % (self.user.id, test_page_url)
        )

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertJSONEqual(
            str(response.content, encoding="utf8"),
            {
                "page_url": test_page_url,
                "user": self.user.id,
                "updated_on": page_in_use.updated_on.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            },
        )

    def test_PageInUse_put(self):
        """
        This unit test tests the update of an existing PageInUse using PUT on route ws/page_in_use/url
        :return:
        """
        # Arrange
        self.login_user()

        # Add a value to database
        page = PageInUse(page_url="foo.com/blah", user=self.user)
        page.save()

        min_update_time = page.created_on + timedelta(seconds=2)

        # sleep so update time can be tested against original time
        time.sleep(2)

        change_page_in_use = {"page_url": "foo.com/blah", "user": self.user.id}

        # Act
        response = self.client.put(
            "/ws/page_in_use_update/foo.com/blah/",
            data=json.dumps(change_page_in_use),
            content_type="application/json",
        )

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        updated_page = PageInUse.objects.filter(page_url="foo.com/blah")
        self.assertTrue(len(updated_page), 1)
        self.assertEqual(page.id, updated_page[0].id)
        self.assertTrue(updated_page[0].updated_on > min_update_time)

    def test_PageInUse_delete(self):
        """
        This unit test tests the delete of an existing PageInUse using DELETE on route ws/page_in_use_delete/
        :return:
        """
        # Arrange
        self.login_user()

        # Add a value to database
        page = PageInUse(page_url="foo.com/blah", user=self.user)
        page.save()

        current_page_in_use_count = PageInUse.objects.all().count()

        # Act
        response = self.client.delete("/ws/page_in_use_delete/%s/" % "foo.com/blah")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        deleted_page_in_use_count = PageInUse.objects.all().count()

        deleted_page = PageInUse.objects.filter(page_url="foo.com/blah")
        self.assertEqual(len(deleted_page), 0)
        self.assertEqual(current_page_in_use_count - 1, deleted_page_in_use_count)

    def test_Campaign_get(self):
        """
        Test getting a Campaign object
        :return:
        """
        # Arrange
        self.login_user()

        # create 2 campaigns
        self.campaign = Campaign(
            title="TextCampaign",
            slug="slug1",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        self.campaign2 = Campaign(
            title="TextCampaign2",
            slug="slug2",
            description="Campaign2 Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign2.save()

        # Act
        response = self.client.get("/ws/campaign/slug2/")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertJSONEqual(
            str(response.content, encoding="utf8"),
            {
                "description": "Campaign2 Description",
                "end_date": None,
                "id": self.campaign2.id,
                "slug": "slug2",
                "start_date": None,
                "status": Status.EDIT,
                "s3_storage": False,
                "title": "TextCampaign2",
                "projects": [],
                "assets": [],
            },
        )

    def test_Campaign_delete(self):
        """
        Test deleting a Campaign object
        :return:
        """
        # Arrange
        self.login_user()

        # create 2 campaigns
        self.campaign = Campaign(
            title="TextCampaign",
            slug="slug1",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        self.campaign2 = Campaign(
            title="TextCampaign2",
            slug="slug2",
            description="Campaign2 Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign2.save()

        current_campaign_count = Campaign.objects.all().count()

        # Act
        response = self.client.delete("/ws/campaign_delete/slug2/")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        deleted_campaign_count = Campaign.objects.all().count()
        self.assertEqual(current_campaign_count - 1, deleted_campaign_count)

    def test_Campaign_by_id_get(self):
        """
        Test getting a Campaign object by id
        :return:
        """
        # Arrange
        self.login_user()

        # create 2 campaigns
        self.campaign = Campaign(
            title="TextCampaign",
            slug="slug1",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        self.campaign2 = Campaign(
            title="TextCampaign2",
            slug="slug2",
            description="Campaign2 Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign2.save()

        # Act
        response = self.client.get("/ws/campaign_by_id/%s/" % self.campaign2.id)

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertJSONEqual(
            str(response.content, encoding="utf8"),
            {
                "description": "Campaign2 Description",
                "end_date": None,
                "id": self.campaign2.id,
                "slug": "slug2",
                "start_date": None,
                "status": Status.EDIT,
                "s3_storage": False,
                "title": "TextCampaign2",
                "projects": [],
                "assets": [],
            },
        )

    def test_get_assets_by_item(self):
        """
        Test getting a list of assets by item
        :return:
        """

        self.login_user()

        # Create a campaign
        self.campaign = Campaign(
            title="TextCampaign",
            slug="slug1",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        # Create a project
        self.project = Project(
            title="A Project", slug="project-slug", campaign=self.campaign
        )
        self.project.save()

        # Create two items
        self.item1 = Item(
            title="item1",
            slug="item1",
            item_id="item1",
            campaign=self.campaign,
            project=self.project,
        )
        self.item1.save()

        self.item2 = Item(
            title="item2",
            slug="item2",
            item_id="item2",
            campaign=self.campaign,
            project=self.project,
        )
        self.item2.save()

        # Add 2 assets to item2, 1 asset to item1
        self.asset = Asset(
            title="TestAsset",
            slug="Asset1",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
            item=self.item1,
        )
        self.asset.save()

        self.asset2 = Asset(
            title="TestAsset2",
            slug="Asset2",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
            item=self.item1,
        )
        self.asset2.save()

        self.asset3 = Asset(
            title="TestAsset3",
            slug="Asset3",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
            item=self.item2,
        )
        self.asset3.save()

        # Act
        response = self.client.get("/ws/item_by_id/item1/")

        json_resp = json.loads(response.content)

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(json_resp["assets"]), 2)

    def test_get_assets_by_campaign(self):
        """
        Test getting a list of assets by campaign
        :return:
        """

        # Arrange
        self.login_user()

        # create 2 campaigns
        self.campaign = Campaign(
            title="TextCampaign",
            slug="slug1",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        self.campaign2 = Campaign(
            title="TextCampaign2",
            slug="slug2",
            description="Campaign2 Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign2.save()

        # Add 2 assets to campaign2, 1 asset to campaign1
        self.asset = Asset(
            title="TestAsset",
            slug="Asset1",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign2,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        self.asset2 = Asset(
            title="TestAsset2",
            slug="Asset2",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign2,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset2.save()

        self.asset3 = Asset(
            title="TestAsset3",
            slug="Asset3",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset3.save()

        # Act
        response = self.client.get("/ws/asset/slug2/")

        json_resp = json.loads(response.content)

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(json_resp["results"]), 2)

    def test_Asset_Update_put(self):
        """
        Test updating an asset by campaign and slug to inactive
        :return:
        """

        # Arrange
        self.login_user()
        self.maxDiff = None

        self.campaign = Campaign(
            title="TextCampaign",
            slug="slug1",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        self.asset = Asset(
            title="TestAsset",
            slug="Asset1",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        expected_response = {
            "id": self.asset.id,
            "title": "TestAsset3",
            "slug": "Asset3",
            "description": "Asset Description",
            "media_url": "http://www.foo.com/1/2/3",
            "media_type": "IMG",
            "campaign": {
                "id": self.campaign.id,
                "slug": "slug1",
                "title": "TextCampaign",
                "description": "Campaign Description",
                "s3_storage": False,
                "start_date": None,
                "end_date": None,
                "status": "Edit",
                "projects": [],
                "assets": [
                    {
                        "title": "TestAsset3",
                        "slug": "Asset3",
                        "description": "Asset Description",
                        "media_url": "http://www.foo.com/1/2/3",
                        "media_type": "IMG",
                        "sequence": 1,
                        "metadata": {"key": "val2"},
                        "status": "Edit",
                    }
                ],
            },
            "project": None,
            "sequence": 1,
            "metadata": {"key": "val2"},
            "status": "Edit",
        }

        # Act

        asset_update = {"campaign": self.campaign.slug, "slug": self.asset.slug}

        # Act
        response = self.client.put(
            "/ws/asset_update/%s/%s/" % (self.campaign.slug, self.asset.slug),
            data=json.dumps(asset_update),
            content_type="application/json",
        )

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        updated_asset = Asset.objects.get(slug=self.asset.slug)
        self.assertEqual(updated_asset.status, Status.INACTIVE)

    def test_get_assets_by_campaign_and_slug(self):
        """
        Test getting an asset by campaign and slug
        :return:
        """

        # Arrange
        self.login_user()
        self.maxDiff = None

        # create 2 campaigns
        self.campaign = Campaign(
            title="TextCampaign",
            slug="slug1",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        self.campaign2 = Campaign(
            title="TextCampaign2",
            slug="slug2",
            description="Campaign2 Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign2.save()

        # Add 2 assets to campaign2, 1 asset to campaign1
        self.asset = Asset(
            title="TestAsset",
            slug="Asset1",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign2,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        self.asset2 = Asset(
            title="TestAsset2",
            slug="Asset2",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign2,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset2.save()

        self.asset3 = Asset(
            title="TestAsset3",
            slug="Asset3",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset3.save()

        expected_response = {
            "id": self.asset3.id,
            "title": "TestAsset3",
            "slug": "Asset3",
            "description": "Asset Description",
            "media_url": "http://www.foo.com/1/2/3",
            "media_type": "IMG",
            "campaign": {
                "id": self.campaign.id,
                "slug": "slug1",
                "title": "TextCampaign",
                "description": "Campaign Description",
                "s3_storage": False,
                "start_date": None,
                "end_date": None,
                "status": "Edit",
                "projects": [],
                "assets": [
                    {
                        "id": self.asset3.id,
                        "title": "TestAsset3",
                        "slug": "Asset3",
                        "description": "Asset Description",
                        "media_url": "http://www.foo.com/1/2/3",
                        "media_type": "IMG",
                        "sequence": 1,
                        "metadata": {"key": "val2"},
                        "status": "Edit",
                    }
                ],
            },
            "project": None,
            "sequence": 1,
            "metadata": {"key": "val2"},
            "status": "Edit",
        }

        # Act
        response = self.client.get("/ws/asset_by_slug/slug1/Asset3/")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertJSONEqual(force_text(response.content), expected_response)

    def test_get_assets_by_campaign_and_slug_no_match(self):
        """
        Test getting an asset by campaign and slug using a slug that doesn't exist
        :return:
        """

        # Arrange
        self.login_user()

        # create 2 campaigns
        self.campaign = Campaign(
            title="TextCampaign",
            slug="slug1",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        self.campaign2 = Campaign(
            title="TextCampaign2",
            slug="slug2",
            description="Campaign2 Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign2.save()

        # Add 2 assets to campaign2, 1 asset to campaign1
        self.asset = Asset(
            title="TestAsset",
            slug="Asset1",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign2,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        self.asset2 = Asset(
            title="TestAsset2",
            slug="Asset2",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign2,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset2.save()

        self.asset3 = Asset(
            title="TestAsset3",
            slug="Asset3",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset3.save()

        # Act
        response = self.client.get("/ws/asset_by_slug/slugxxx/Asset3xxx/")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertJSONEqual(
            force_text(response.content),
            {
                "title": "",
                "slug": "",
                "description": "",
                "media_url": "",
                "media_type": None,
                "campaign": {
                    "description": "",
                    "end_date": None,
                    "s3_storage": False,
                    "slug": "",
                    "start_date": None,
                    "status": None,
                    "assets": [],
                    "projects": [],
                    "title": "",
                },
                "sequence": None,
                "metadata": None,
                "project": {
                    "metadata": None,
                    "slug": "",
                    "is_publish": False,
                    "status": None,
                    "title": "",
                },
                "status": None,
            },
        )

    def test_PageInUse_filter_get(self):
        """
        Test the route ws/page_in_use_filter/user/page_url/
        It should return a list of PageInUse updated in last 5 minutes by user other than self.user
        :return:
        """

        # Arrange
        self.login_user()

        # create a second user
        username = "tester2"
        test_url = "bar.com/blah"
        self.user2 = User.objects.create(username=username, email="tester2@foo.com")
        self.user2.set_password("top_secret")
        self.user2.save()

        # Add values to database
        PageInUse.objects.create(page_url="foo.com/blah", user=self.user)

        PageInUse.objects.create(page_url=test_url, user=self.user2)

        # Act
        response = self.client.get(
            "/ws/page_in_use_filter/%s/%s/" % (self.user.username, test_url)
        )

        json_resp = json.loads(response.content)

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(json_resp["results"]) > 0)

    def test_PageInUse_filter_no_pages_get(self):
        """
        Test the route ws/page_in_use_filter/user/page_url/
        It should return an empty list
        :return:
        """

        # Arrange
        self.login_user()

        # create a second user
        username = "tester2"
        test_url = "bar.com/blah"
        self.user2 = User.objects.create(username=username, email="tester2@foo.com")
        self.user2.set_password("top_secret")
        self.user2.save()

        # Act
        response = self.client.get(
            "/ws/page_in_use_filter/%s/%s/" % (self.user.username, test_url)
        )

        json_resp = json.loads(response.content)

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(json_resp["results"]), 0)

    def test_Transcriptions_latest_get(self):
        """
        Test getting latest transcription for an asset. route ws/transcriptions/asset/
        :return:
        """

        # Arrange
        self.login_user()

        # create a second user
        username = "tester2"
        self.user2 = User.objects.create(username=username, email="tester2@foo.com")
        self.user2.set_password("top_secret")
        self.user2.save()

        # create a campaign
        self.campaign = Campaign(
            title="TextCampaign",
            slug="www.foo.com/slug2",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        # create Assets
        self.asset = Asset(
            title="TestAsset",
            slug="www.foo.com/slug1",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        self.asset2 = Asset(
            title="TestAsset2",
            slug="www.foo.com/slug2",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset2.save()

        # add Transcription objects
        self.transcription = Transcription(
            asset=self.asset, user_id=self.user.id, status=Status.EDIT, text="T1"
        )
        self.transcription.save()

        t2_text = "T2"

        self.transcription2 = Transcription(
            asset=self.asset, user_id=self.user2.id, status=Status.EDIT, text=t2_text
        )
        self.transcription2.save()

        # Act

        response = self.client.get("/ws/transcription/%s/" % self.asset.id)

        json_resp = json.loads(response.content)

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(json_resp["text"], t2_text)

    def test_Transcriptions_by_user(self):
        """
        Test getting the user's transcriptions. route ws/transcription_by_user/<userid>/
        :return:
        """

        # Arrange
        self.login_user()

        # create a second user
        username = "tester2"
        self.user2 = User.objects.create(username=username, email="tester2@foo.com")
        self.user2.set_password("top_secret")
        self.user2.save()

        # create a campaign
        self.campaign = Campaign(
            title="TextCampaign",
            slug="www.foo.com/slug2",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        # create Assets
        self.asset = Asset(
            title="TestAsset",
            slug="www.foo.com/slug1",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        self.asset2 = Asset(
            title="TestAsset2",
            slug="www.foo.com/slug2",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset2.save()

        # add Transcription objects
        t1_text = "T1"
        self.transcription = Transcription(
            asset=self.asset, user_id=self.user.id, status=Status.EDIT, text=t1_text
        )
        self.transcription.save()

        t2_text = "T2"

        self.transcription2 = Transcription(
            asset=self.asset, user_id=self.user2.id, status=Status.EDIT, text=t2_text
        )
        self.transcription2.save()

        t3_text = "T3"

        self.transcription3 = Transcription(
            asset=self.asset, user_id=self.user.id, status=Status.EDIT, text=t3_text
        )
        self.transcription3.save()

        # Act

        response = self.client.get("/ws/transcription_by_user/%s/" % self.user.id)

        json_resp = json.loads(response.content)
        transcriptions_array = []
        for trans in json_resp["results"]:
            transcriptions_array.append(trans["text"])

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(json_resp["count"], 2)
        self.assertTrue("T3" in transcriptions_array)
        self.assertTrue("T1" in transcriptions_array)
        self.assertFalse("T2" in transcriptions_array)

    def test_Transcriptions_create_post(self):
        """
        Test creating a transcription. route ws/transcription_create/
        :return:
        """
        # Arrange
        self.login_user()

        # create a campaign
        self.campaign = Campaign(
            title="TextCampaign",
            slug="www.foo.com/slug2",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        # create Assets
        self.asset = Asset(
            title="TestAsset",
            slug="www.foo.com/slug1",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        # Act
        response = self.client.post(
            "/ws/transcription_create/",
            {
                "asset": self.asset.id,
                "user_id": self.user.id,
                "status": Status.EDIT,
                "text": "T1",
            },
        )

        # Assert
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Get all Transcriptions for the asset
        transcriptions_count = Transcription.objects.filter(asset=self.asset).count()
        self.assertEqual(transcriptions_count, 1)

        # Add Another transcription
        response = self.client.post(
            "/ws/transcription_create/",
            {
                "asset": self.asset.id,
                "user_id": self.user.id,
                "status": Status.EDIT,
                "text": "T2",
            },
        )

        # Get all Transcriptions for the asset, should be another one
        transcriptions_count = Transcription.objects.filter(asset=self.asset).count()
        self.assertEqual(transcriptions_count, 2)

    def test_Tag_create_post(self):
        """
        Test creating a tag. route ws/tag_create/
        :return:
        """
        # Arrange
        self.login_user()

        # create a campaign
        self.campaign = Campaign(
            title="TextCampaign",
            slug="www.foo.com/slug2",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        # create Assets
        self.asset = Asset(
            title="TestAsset",
            slug="www.foo.com/slug1",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        # Act
        response = self.client.post(
            "/ws/tag_create/",
            {
                "campaign": self.campaign.slug,
                "asset": self.asset.slug,
                "user_id": self.user.id,
                "name": "T1",
                "value": "T1",
            },
        )

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_Tag_delete(self):
        """
        Test deleting a tag. route ws/tag_/
        :return:
        """
        # Arrange
        self.login_user()

        # create a campaign
        self.campaign = Campaign(
            title="TextCampaign",
            slug="campaignslug",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        # create Assets
        self.asset = Asset(
            title="TestAsset",
            slug="assetslug1",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        self.tag1 = Tag(name="Tag1", value="Tag1")
        self.tag1.save()

        self.tag2 = Tag(name="Tag2", value="Tag2")
        self.tag2.save()

        # Save for User1
        self.asset_tag_collection = UserAssetTagCollection(
            asset=self.asset, user_id=self.user.id
        )
        self.asset_tag_collection.save()
        self.asset_tag_collection.tags.add(self.tag1, self.tag2)

        # Act
        url = "/ws/tag_delete/%s/%s/%s/%s/" % (
            self.campaign.slug,
            self.asset.slug,
            "Tag1",
            self.user.id,
        )
        response = self.client.delete(url, follow=True)

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # verify only 1 tag in db
        remaining_tags = Tag.objects.all()
        self.assertEqual(len(remaining_tags), 1)

    def test_Tag_create_with_an_existing_tag_post(self):
        """
        Test creating a tag, adding to an asset that already has a tag. route ws/tag_create/
        :return:
        """
        # Arrange
        self.login_user()

        # create a campaign
        self.campaign = Campaign(
            title="TextCampaign",
            slug="www.foo.com/slug2",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        # create Assets
        self.asset = Asset(
            title="TestAsset",
            slug="www.foo.com/slug1",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        # Act
        response = self.client.post(
            "/ws/tag_create/",
            {
                "campaign": self.campaign.slug,
                "asset": self.asset.slug,
                "user_id": self.user.id,
                "name": "T1",
                "value": "T1",
            },
        )

        response = self.client.post(
            "/ws/tag_create/",
            {
                "campaign": self.campaign.slug,
                "asset": self.asset.slug,
                "user_id": self.user.id,
                "name": "T2",
                "value": "T3",
            },
        )

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_GetTags_get(self):
        """
        Test getting the tags for an asset, route /ws/tags/<asset>
        :return:
        """

        # Arrange
        self.login_user()

        # create a second user
        username = "tester2"
        self.user2 = User.objects.create(username=username, email="tester2@foo.com")
        self.user2.set_password("top_secret")
        self.user2.save()

        # create a campaign
        self.campaign = Campaign(
            title="TextCampaign",
            slug="www.foo.com/slug2",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        # create Assets
        self.asset = Asset(
            title="TestAsset",
            slug="www.foo.com/slug1",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        self.tag1 = Tag(name="Tag1", value="Tag1")
        self.tag1.save()

        self.tag2 = Tag(name="Tag2", value="Tag2")
        self.tag2.save()

        self.tag3 = Tag(name="Tag3", value="Tag3")
        self.tag3.save()

        # Save for User1
        self.asset_tag_collection = UserAssetTagCollection(
            asset=self.asset, user_id=self.user.id
        )
        self.asset_tag_collection.save()
        self.asset_tag_collection.tags.add(self.tag1, self.tag2)

        # Save for User2
        self.asset_tag_collection2 = UserAssetTagCollection(
            asset=self.asset, user_id=self.user2.id
        )
        self.asset_tag_collection2.save()
        self.asset_tag_collection2.tags.add(self.tag3)

        # Act
        response = self.client.get("/ws/tags/%s/" % self.asset.id)

        json_resp = json.loads(response.content)

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(json_resp["results"]), 3)

    def test_GetTags_notags_get(self):
        """
        Test getting the tags for an asset when no tags exist, route /ws/tags/<asset>
        :return:
        """

        # Arrange
        self.login_user()

        # create a second user
        username = "tester2"
        self.user2 = User.objects.create(username=username, email="tester2@foo.com")
        self.user2.set_password("top_secret")
        self.user2.save()

        # create a campaign
        self.campaign = Campaign(
            title="TextCampaign",
            slug="www.foo.com/slug2",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        # create Assets
        self.asset = Asset(
            title="TestAsset",
            slug="www.foo.com/slug1",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        # Act
        response = self.client.get("/ws/tags/%s/" % self.asset.id)

        json_resp = json.loads(response.content)

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(json_resp["results"]), 0)
