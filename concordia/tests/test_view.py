# TODO: Add correct copyright header

import logging
import re
import tempfile
import time
from unittest.mock import Mock, patch

import responses
from captcha.models import CaptchaStore
from django.test import Client, TestCase
from PIL import Image

from concordia.models import (Asset, Campaign, MediaType, PageInUse, Project, Status,
                              Tag, Transcription, User, UserAssetTagCollection,
                              UserProfile)

import views

logging.disable(logging.CRITICAL)


class ViewTest_Concordia(TestCase):
    """
    This class contains the unit tests for the view in the concordia app.

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

    def add_page_in_use_mocks(self, responses):
        """
        Set up the mock function calls for REST calls for page_in_use
        :param responses:
        :return:
        """

        responses.add(
            responses.GET,
            "http://testserver/ws/page_in_use_filter/tester//campaigns/Campaign1/asset/Asset1//",
            json={"count": 0, "results": []},
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/page_in_use_count/%s//campaigns/Campaign1/asset/Asset1//" %
            (self.user.id if hasattr(self, "user") else self.anon_user.id,),
            json={"page_in_use": False},
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/page_in_use_user/%s//campaigns/Campaign1/asset/Asset1//" %
            (self.user.id if hasattr(self, "user") else self.anon_user.id,),
            json={"user": self.user.id if hasattr(self, "user") else self.anon_user.id},
            status=200
        )

    def test_concordia_api(self):
        """
        Test the tracribr_api. Provide a mock of requests
        :return:
        """

        # Arrange

        with patch("views.requests") as mock_requests:
            mock_requests.get.return_value = mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"concordia_data": "abc123456"}

            # Act
            results = views.concordia_api("relative_path")

            # Assert
            self.assertEqual(results["concordia_data"], "abc123456")

    def test_login_with_email(self):
        """
        Test the login is successful with email
        :return:
        """
        # Arrange
        user = User.objects.create(username="etester", email="etester@foo.com")
        user.set_password("top_secret")
        user.save()

        # Act
        user = self.client.login(username="etester@foo.com", password="top_secret")

        # Assert
        self.assertTrue(user)

    @patch("concordia.views.requests")
    def test_AccountProfileView_get(self, mock_requests):
        """
        Test the http GET on route account/profile
        :return:
        """

        # Arrange
        mock_requests.get.return_value.status_code = 200
        mock_requests.get.return_value.json.return_value = {
            "concordia_data": "abc123456"
        }
        mock_requests.get.return_value.content = (
            b'{"count":0,"next":null,"previous":null,"results":[]}'
        )

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

        # create an Asset
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

        # add a Transcription object
        self.transcription = Transcription(
            asset=self.asset, user_id=self.user.id, status=Status.EDIT
        )
        self.transcription.save()

        # Act

        # Act
        response = self.client.get("/account/profile/")

        # Assert

        # validate the web page has the "tester" and "tester@foo.com" as values
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="profile.html")

    @patch("concordia.views.requests")
    def test_AccountProfileView_post(self, mock_requests):
        """
        This unit test tests the post entry for the route account/profile
        :param self:
        :return:
        """

        test_email = "tester@foo.com"

        # Arrange
        self.login_user()

        mock_requests.get.return_value.status_code = 200
        mock_requests.get.return_value.json.return_value = {
            "concordia_data": "abc123456"
        }
        mock_requests.get.return_value.content = (
            b'{"count":0,"next":null,"previous":null,"results":[]}'
        )

        # Act
        response = self.client.post(
            "/account/profile/",
            {
                "email": test_email,
                "username": "tester",
                "password1": "!Abc12345",
                "password2": "!Abc12345",
            },
        )

        # Assert
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/account/profile/")

        # Verify the User was correctly updated
        updated_user = User.objects.get(email=test_email)
        self.assertEqual(updated_user.email, test_email)

    @patch("concordia.views.requests")
    def test_AccountProfileView_post_invalid_form(self, mock_requests):
        """
        This unit test tests the post entry for the route account/profile but submits an invalid form
        :param self:
        :return:
        """

        # Arrange
        self.login_user()
        mock_requests.get.return_value.status_code = 200
        mock_requests.get.return_value.json.return_value = {
            "concordia_data": "abc123456"
        }
        mock_requests.get.return_value.content = (
            b'{"count":0,"next":null,"previous":null,"results":[]}'
        )

        # Act
        response = self.client.post("/account/profile/", {"first_name": "Jimmy"})

        # Assert
        self.assertEqual(response.status_code, 302)

        # Verify the User was not changed
        updated_user = User.objects.get(id=self.user.id)
        self.assertEqual(updated_user.first_name, "")

    @patch("concordia.views.requests")
    def test_AccountProfileView_post_new_password(self, mock_requests):
        """
        This unit test tests the post entry for the route account/profile with new password
        :param self:
        :return:
        """

        # Arrange
        self.login_user()
        mock_requests.get.return_value.status_code = 200
        mock_requests.get.return_value.json.return_value = {
            "concordia_data": "abc123456"
        }
        mock_requests.get.return_value.content = (
            b'{"count":0,"next":null,"previous":null,"results":[]}'
        )

        test_email = "tester@foo.com"

        # Act
        response = self.client.post(
            "/account/profile/",
            {
                "email": test_email,
                "username": "tester",
                "password1": "aBc12345!",
                "password2": "aBc12345!",
            },
        )

        # Assert
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/account/profile/")

        # Verify the User was correctly updated
        updated_user = User.objects.get(email=test_email)
        self.assertEqual(updated_user.email, test_email)

        # logout and login with new password
        self.client.logout()
        login2 = self.client.login(username="tester", password="aBc12345!")

        self.assertTrue(login2)

    @patch("concordia.views.requests")
    def test_AccountProfileView_post_with_image(self, mock_requests):
        """
        This unit test tests the post entry for the
        route account/profile with new image file
        :param self:
        :return:
        """

        # Arrange
        self.login_user()
        mock_requests.get.return_value.status_code = 200
        mock_requests.get.return_value.json.return_value = {
            "concordia_data": "abc123456"
        }
        mock_requests.get.return_value.content = (
            b'{"count":0,"next":null,"previous":null,"results":[]}'
        )

        pw = "!Abc12345"

        existing_userprofile_count = UserProfile.objects.all().count()

        # Act
        image = Image.new("RGBA", size=(50, 50), color=(155, 0, 0))
        file = tempfile.NamedTemporaryFile(suffix=".png")
        image.save(file)

        with open(file.name, encoding="ISO-8859-1") as fp:

            response = self.client.post(
                "/account/profile/",
                {
                    "myfile": fp,
                    "email": "tester@foo.com",
                    "username": "tester",
                    "password1": pw,
                    "password2": pw,
                },
            )

            # Assert
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, "/account/profile/")

            # Verify the UserProfile was correctly updated, a new entry in db exists
            profile = UserProfile.objects.all()

            self.assertEqual(len(profile), existing_userprofile_count + 1)

    @patch("concordia.views.requests")
    def test_concordiaView(self, mock_requests):
        """
        Test the GET method for route /campaigns
        :return:
        """
        # Arrange

        mock_requests.get.return_value.status_code = 200
        mock_requests.get.return_value.json.return_value = {
            "concordia_data": "abc123456"
        }

        # Act
        response = self.client.get("/campaigns/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="transcriptions/campaigns.html")

    @responses.activate
    def test_concordiaCampaignView_get(self):
        """
        Test GET on route /campaigns/<slug-value> (campaign)
        :return:
        """

        # Arrange

        # add an item to Campaign
        self.campaign = Campaign(
            title="TextCampaign",
            slug="test-slug2",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        # mock REST requests

        campaign_json = {
            "id": self.campaign.id,
            "slug": "test-slug2",
            "title": "TextCampaign",
            "description": "Campaign Description",
            "s3_storage": True,
            "start_date": None,
            "end_date": None,
            "status": Status.EDIT,
            "assets": [],
            "projects": [],
        }

        responses.add(
            responses.GET,
            "http://testserver/ws/campaign/test-slug2/",
            json=campaign_json,
            status=200,
        )

        # Act
        response = self.client.get("/campaigns/test-slug2/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="transcriptions/campaign.html")

    @responses.activate
    def test_concordiaCampaignView_get_page2(self):
        """
        Test GET on route /campaigns/<slug-value>/ (campaign) on page 2
        :return:
        """

        # Arrange

        # add an item to Campaign
        self.campaign = Campaign(
            title="TextCampaign",
            slug="test-slug2",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        # mock REST requests

        campaign_json = {
            "id": self.campaign.id,
            "slug": "test-slug2",
            "title": "TextCampaign",
            "description": "Campaign Description",
            "s3_storage": True,
            "start_date": None,
            "end_date": None,
            "status": Status.EDIT,
            "assets": [],
            "projects": [],
        }

        responses.add(
            responses.GET,
            "http://testserver/ws/campaign/test-slug2/",
            json=campaign_json,
            status=200,
        )

        # Act
        response = self.client.get("/campaigns/test-slug2/", {"page": 2})

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="transcriptions/campaign.html")

    def test_ExportCampaignView_get(self):
        """
        Test GET route /campaigns/export/<slug-value>/ (campaign)
        :return:
        """

        # Arrange

        self.campaign = Campaign(
            title="TextCampaign",
            slug="slug2",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        self.asset = Asset(
            title="TestAsset",
            slug="test-slug2",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        # Act
        response = self.client.get("/campaigns/exportCSV/slug2/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            str(response.content),
            "b'Campaign,Title,Description,MediaUrl,Transcription,Tags\\r\\n"
            "TextCampaign,TestAsset,Asset Description,"
            "http://www.foo.com/1/2/3,,\\r\\n'",
        )

    @responses.activate
    def test_DeleteCampaign_get(self):
        """
        Test GET route /campaigns/delete/<slug-value>/ (campaign)
        :return:
        """

        # Arrange

        # add an item to Campaign
        self.campaign = Campaign(
            title="TextCampaign",
            slug="test-slug2",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        self.asset = Asset(
            title="TestAsset",
            slug="test-slug2",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        # Mock REST api calls
        responses.add(responses.DELETE,
                      "http://testserver/ws/campaign_delete/%s/" % (self.campaign.slug, ),
                      status=200)



        # Act

        response = self.client.get("/campaigns/delete/test-slug2", follow=False)

        # Assert
        self.assertEqual(response.status_code, 301)

    @responses.activate
    def test_DeleteAsset_get(self):
        """
        Test GET route /campaigns/delete/asset/<slug-value>/ (asset)
        :return:
        """

        # Arrange

        # add an item to Campaign
        self.campaign = Campaign(
            title="TextCampaign",
            slug="test-campaign-slug",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        self.asset = Asset(
            title="TestAsset",
            slug="test-asset-slug",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        self.asset = Asset(
            title="TestAsset1",
            slug="test-asset-slug1",
            description="Asset Description1",
            media_url="http://www.foo1.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.asset.save()

        # Mock REST calls
        campaign_json = {
            "id": self.campaign.id,
            "slug": self.campaign.slug,
            "title": "TextCampaign",
            "description": "Campaign Description",
            "s3_storage": True,
            "start_date": None,
            "end_date": None,
            "status": Status.EDIT,
            "assets": [],
        }

        responses.add(
            responses.GET,
            "http://testserver/ws/campaign/%s/" % (self.campaign.slug, ),
            json=campaign_json,
            status=200,
        )

        responses.add(responses.PUT,
                      "http://testserver/ws/asset_update/%s/%s/" % (self.campaign.slug, self.asset.slug, ),
                      status=200)

        # Act

        response = self.client.get("/campaigns/%s/delete/asset/%s/" % (self.campaign.slug, self.asset.slug, ),
                                   ollow=True)

        # Assert
        self.assertEqual(response.status_code, 302)

    @responses.activate
    def test_ConcordiaAssetView_post(self):
        """
        This unit test test the POST route /campaigns/<campaign>/asset/<Asset_name>/
        :return:
        """
        # Arrange
        self.login_user()

        # create a campaign
        self.campaign = Campaign(
            title="TestCampaign",
            slug="Campaign1",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        # create an Asset
        asset_slug = "Asset1"

        self.asset = Asset(
            title="TestAsset",
            slug=asset_slug,
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        # add a Transcription object
        self.transcription = Transcription(
            asset=self.asset,
            user_id=self.user.id,
            text="Test transcription 1",
            status=Status.EDIT,
        )
        self.transcription.save()

        tag_name = "Test tag 1"

        # mock REST requests
        asset_by_slug_response = {
            "id": self.asset.id,
            "title": "TestAsset",
            "slug": asset_slug,
            "description": "mss859430177",
            "media_url": "https://s3.us-east-2.amazonaws.com/chc-collections/test_s3/mss859430177/1.jpg",
            "media_type": MediaType.IMAGE,
            "campaign": {"slug": "Campaign1"},
            "project": None,
            "sequence": 1,
            "metadata": {"key": "val2"},
            "status": Status.EDIT,
        }

        transcription_json = {
            "asset": {
                "title": "",
                "slug": "",
                "description": "",
                "media_url": "",
                "media_type": None,
                "campaign": {
                    "slug": "",
                    "title": "",
                    "description": "",
                    "s3_storage": False,
                    "start_date": None,
                    "end_date": None,
                    "status": None,
                    "assets": [],
                },
                "project": None,
                "sequence": None,
                "metadata": None,
                "status": None,
            },
            "user_id": None,
            "text": "",
            "status": None,
        }

        tag_json = {"results": []}

        responses.add(
            responses.GET,
            "http://testserver/ws/page_in_use_filter/tester//campaigns/Campaign1/asset/Asset1//",
            json={"count": 0, "results": []},
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/asset_by_slug/Campaign1/Asset1/",
            json=asset_by_slug_response,
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/transcription/%s/" % (self.asset.id,),
            json=transcription_json,
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/tags/%s/" % (self.asset.id,),
            json=tag_json,
            status=200,
        )

        responses.add(
            responses.POST, "http://testserver/ws/transcription_create/", status=200
        )
        responses.add(responses.POST, "http://testserver/ws/tag_create/", status=200)

        # Act
        response = self.client.post(
            "/campaigns/Campaign1/asset/Asset1/",
            {"tx": "First Test Transcription", "tags": tag_name, "action": "Save"},
        )

        # Assert
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/campaigns/Campaign1/asset/Asset1/")

    @responses.activate
    def test_ConcordiaAssetView_post_with_just_tagging(self):
        """
        This unit test test the POST route /campaigns/<campaign>/asset/<Asset_name>/
        :return:
        """
        # Arrange
        self.login_user()

        # create a campaign
        self.campaign = Campaign(
            title="TestCampaign",
            slug="Campaign1",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        # create an Asset
        asset_slug = "Asset1"

        self.asset = Asset(
            title="TestAsset",
            slug=asset_slug,
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        # add a Transcription object
        self.transcription = Transcription(
            asset=self.asset,
            user_id=self.user.id,
            text="Test transcription 1",
            status=Status.EDIT,
        )
        self.transcription.save()

        tag_name = "Test tag 1"

        # mock REST requests
        asset_by_slug_response = {
            "id": self.asset.id,
            "title": "TestAsset",
            "slug": asset_slug,
            "description": "mss859430177",
            "media_url": "https://s3.us-east-2.amazonaws.com/chc-collections/test_s3/mss859430177/1.jpg",
            "media_type": MediaType.IMAGE,
            "campaign": {"slug": "Campaign1"},
            "project": None,
            "sequence": 1,
            "metadata": {"key": "val2"},
            "status": Status.EDIT,
        }

        transcription_json = {
            "asset": {
                "title": "",
                "slug": "",
                "description": "",
                "media_url": "",
                "media_type": None,
                "campaign": {
                    "slug": "",
                    "title": "",
                    "description": "",
                    "s3_storage": False,
                    "start_date": None,
                    "end_date": None,
                    "status": None,
                    "assets": [],
                },
                "project": None,
                "sequence": None,
                "metadata": None,
                "status": None,
            },
            "user_id": None,
            "text": "",
            "status": None,
        }

        tag_json = {"results": []}

        responses.add(
            responses.GET,
            "http://testserver/ws/page_in_use_filter/tester//campaigns/Campaign1/asset/Asset1//",
            json={"count": 0, "results": []},
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/asset_by_slug/Campaign1/Asset1/",
            json=asset_by_slug_response,
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/transcription/%s/" % (self.asset.id,),
            json=transcription_json,
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/tags/%s/" % (self.asset.id,),
            json=tag_json,
            status=200,
        )

        responses.add(
            responses.POST, "http://testserver/ws/transcription_create/", status=200
        )
        responses.add(responses.POST, "http://testserver/ws/tag_create/", status=200)

        # Act
        response = self.client.post(
            "/campaigns/Campaign1/asset/Asset1/",
            {"tags": tag_name, "action": "Save", "tagging": "true"},
        )

        # Assert
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/campaigns/Campaign1/asset/Asset1/#tab-tag")

    @responses.activate
    def test_ConcordiaAssetView_post_contact_community_manager(self):
        """
        This unit test test the POST route /campaigns/<campaign>/asset/<Asset_name>/
        for an anonymous user. Clicking the contact community manager button
        should redirect to the contact us page.
        :return:
        """
        # Arrange

        # create a campaign
        self.campaign = Campaign(
            title="TestCampaign",
            slug="Campaign1",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        asset_slug = "Asset1"

        self.asset = Asset(
            title="TestAsset",
            slug=asset_slug,
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        # create anonymous user
        self.anon_user = User.objects.create(username="anonymous", email="tester@foo.com")
        self.anon_user.set_password("blah_anonymous!")
        self.anon_user.save()

        # add a Transcription object
        self.transcription = Transcription(
            asset=self.asset,
            user_id=self.anon_user.id,
            text="Test transcription 1",
            status=Status.EDIT,
        )
        self.transcription.save()

        tag_name = "Test tag 1"

        # mock REST requests
        asset_by_slug_response = {
            "id": self.asset.id,
            "title": "TestAsset",
            "slug": asset_slug,
            "description": "mss859430177",
            "media_url": "https://s3.us-east-2.amazonaws.com/chc-collections/test_s3/mss859430177/1.jpg",
            "media_type": MediaType.IMAGE,
            "campaign": {"slug": "Campaign1"},
            "project": None,
            "sequence": 1,
            "metadata": {"key": "val2"},
            "status": Status.EDIT,
        }

        transcription_json = {
            "asset": {
                "title": "",
                "slug": "",
                "description": "",
                "media_url": "",
                "media_type": None,
                "campaign": {
                    "slug": "",
                    "title": "",
                    "description": "",
                    "s3_storage": False,
                    "start_date": None,
                    "end_date": None,
                    "status": None,
                    "assets": [],
                },
                "project": None,
                "sequence": None,
                "metadata": None,
                "status": None,
            },
            "user_id": None,
            "text": "",
            "status": None,
        }

        anonymous_json = {"id": self.anon_user.id, "username": "anonymous",
                          "password": "pbkdf2_sha256$100000$6lht1V74YYXZ$fagq9FeSFlDfqqikuBRGMcxl1GaBvC7tIO7fiiAkReo=",
                          "first_name": "",
                          "last_name": "", "email": "anonymous@anonymous.com", "is_staff": False, "is_active": True,
                          "date_joined": "2018-08-28T19:05:45.653687Z"}

        tag_json = {"results": []}

        self.add_page_in_use_mocks(responses)

        responses.add(
            responses.GET,
            "http://testserver/ws/page_in_use_filter/AnonymousUser//campaigns/Campaign1/asset/Asset1//",
            json={"count": 0, "results": []},
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/asset_by_slug/Campaign1/Asset1/",
            json=asset_by_slug_response,
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/transcription/%s/" % (self.asset.id,),
            json=transcription_json,
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/tags/%s/" % (self.asset.id,),
            json=tag_json,
            status=200,
        )

        responses.add(
            responses.POST, "http://testserver/ws/transcription_create/", status=200
        )
        responses.add(responses.POST, "http://testserver/ws/tag_create/", status=200)

        responses.add(responses.PUT,
                      "http://testserver/ws/page_in_use_update/%s//campaigns/Campaign1/asset/Asset1//" %
                      (self.anon_user.id, ),
                      status=200)

        responses.add(
            responses.GET,
            "http:////testserver/ws/anonymous_user/",
            json=anonymous_json,
            status=200
        )


        # Act
        response = self.client.get("/campaigns/Campaign1/asset/Asset1/")
        self.assertEqual(response.status_code, 200)

        hash_ = re.findall(r'value="([0-9a-f]+)"', str(response.content))[0]
        captcha_response = CaptchaStore.objects.get(hashkey=hash_).response

        response = self.client.post(
            "/campaigns/Campaign1/asset/Asset1/",
            {
                "tx": "First Test Transcription 1",
                "tags": "",
                "action": "contact a manager",
                "captcha_0": hash_,
                "captcha_1": captcha_response,
            },
        )

        # Assert
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/contact/?pre_populate=true")

    @responses.activate
    def test_ConcordiaAssetView_post_anonymous_happy_path(self):
        """
        This unit test test the POST route /campaigns/<campaign>/asset/<Asset_name>/
        for an anonymous user. This user should not be able to tag
        :return:
        """
        # Arrange

        # create a campaign
        self.campaign = Campaign(
            title="TestCampaign",
            slug="Campaign1",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        # create an Asset
        asset_slug = "Asset1"
        self.asset = Asset(
            title="TestAsset",
            slug=asset_slug,
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        # create anonymous user
        self.anon_user = User.objects.create(username="anonymous", email="tester@foo.com")
        self.anon_user.set_password("blah_anonymous!")
        self.anon_user.save()

        # add a Transcription object
        self.transcription = Transcription(
            asset=self.asset,
            user_id=self.anon_user.id,
            text="Test transcription 1",
            status=Status.EDIT,
        )
        self.transcription.save()

        tag_name = "Test tag 1"

        # mock REST requests
        asset_by_slug_response = {
            "id": self.asset.id,
            "title": "TestAsset",
            "slug": asset_slug,
            "description": "mss859430177",
            "media_url": "https://s3.us-east-2.amazonaws.com/chc-collections/test_s3/mss859430177/1.jpg",
            "media_type": MediaType.IMAGE,
            "campaign": {"slug": "Campaign1"},
            "project": None,
            "sequence": 1,
            "metadata": {"key": "val2"},
            "status": Status.EDIT,
        }

        transcription_json = {
            "asset": {
                "title": "",
                "slug": "",
                "description": "",
                "media_url": "",
                "media_type": None,
                "campaign": {
                    "slug": "",
                    "title": "",
                    "description": "",
                    "s3_storage": False,
                    "start_date": None,
                    "end_date": None,
                    "status": None,
                    "assets": [],
                },
                "project": None,
                "sequence": None,
                "metadata": None,
                "status": None,
            },
            "user_id": None,
            "text": "",
            "status": None,
        }

        anonymous_json = {"id": self.anon_user.id, "username": "anonymous",
                          "password": "pbkdf2_sha256$100000$6lht1V74YYXZ$fagq9FeSFlDfqqikuBRGMcxl1GaBvC7tIO7fiiAkReo=",
                          "first_name": "",
                          "last_name": "", "email": "anonymous@anonymous.com", "is_staff": False, "is_active": True,
                          "date_joined": "2018-08-28T19:05:45.653687Z"}

        tag_json = {"results": []}

        self.add_page_in_use_mocks(responses)

        responses.add(
            responses.GET,
            "http://testserver/ws/page_in_use_filter/AnonymousUser//campaigns/Campaign1/asset/Asset1//",
            json={"count": 0, "results": []},
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/asset_by_slug/Campaign1/Asset1/",
            json=asset_by_slug_response,
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/transcription/%s/" % (self.asset.id,),
            json=transcription_json,
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/tags/%s/" % (self.asset.id,),
            json=tag_json,
            status=200,
        )

        responses.add(
            responses.POST, "http://testserver/ws/transcription_create/", status=200
        )
        responses.add(responses.POST, "http://testserver/ws/tag_create/", status=200)

        responses.add(responses.PUT,
                      "http://testserver/ws/page_in_use_update/%s//campaigns/Campaign1/asset/Asset1//" %
                      (self.anon_user.id, ),
                      status=200)

        responses.add(
            responses.GET,
            "http:////testserver/ws/anonymous_user/",
            json=anonymous_json,
            status=200
        )

        # Act
        response = self.client.get("/campaigns/Campaign1/asset/Asset1/")
        self.assertEqual(response.status_code, 200)
        hash_ = re.findall(r'value="([0-9a-f]+)"', str(response.content))[0]
        captcha_response = CaptchaStore.objects.get(hashkey=hash_).response

        response = self.client.post(
            "/campaigns/Campaign1/asset/Asset1/",
            {
                "tx": "First Test Transcription 1",
                "tags": tag_name,
                "action": "Save",
                "captcha_0": hash_,
                "captcha_1": captcha_response,
            },
        )

        # Assert
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/campaigns/Campaign1/asset/Asset1/")

    @responses.activate
    def test_ConcordiaAssetView_post_anonymous_invalid_captcha(self):
        """
        This unit test test the POST route /campaigns/<campaign>/asset/<Asset_name>/
        for an anonymous user with missing captcha. This user should not be able to tag
        also
        :return:
        """
        # Arrange

        # create a campaign
        self.campaign = Campaign(
            title="TestCampaign",
            slug="Campaign1",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        # create an Asset
        asset_slug = "Asset1"
        self.asset = Asset(
            title="TestAsset",
            slug=asset_slug,
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        # create anonymous user
        self.anon_user = User.objects.create(username="anonymous", email="tester@foo.com")
        self.anon_user.set_password("blah_anonymous!")
        self.anon_user.save()

        # add a Transcription object
        self.transcription = Transcription(
            asset=self.asset,
            user_id=self.anon_user.id,
            text="Test transcription 1",
            status=Status.EDIT,
        )
        self.transcription.save()

        # mock REST requests
        asset_by_slug_response = {
            "id": self.asset.id,
            "title": "TestAsset",
            "slug": asset_slug,
            "description": "mss859430177",
            "media_url": "https://s3.us-east-2.amazonaws.com/chc-collections/test_s3/mss859430177/1.jpg",
            "media_type": MediaType.IMAGE,
            "campaign": {"slug": "Campaign1"},
            "project": None,
            "sequence": 1,
            "metadata": {"key": "val2"},
            "status": Status.EDIT,
        }

        transcription_json = {
            "asset": {
                "title": "",
                "slug": "",
                "description": "",
                "media_url": "",
                "media_type": None,
                "campaign": {
                    "slug": "",
                    "title": "",
                    "description": "",
                    "s3_storage": False,
                    "start_date": None,
                    "end_date": None,
                    "status": None,
                    "assets": [],
                },
                "project": None,
                "sequence": None,
                "metadata": None,
                "status": None,
            },
            "user_id": None,
            "text": "",
            "status": None,
        }

        anonymous_json = {"id": self.anon_user.id, "username": "anonymous",
                          "password": "pbkdf2_sha256$100000$6lht1V74YYXZ$fagq9FeSFlDfqqikuBRGMcxl1GaBvC7tIO7fiiAkReo=",
                          "first_name": "",
                          "last_name": "", "email": "anonymous@anonymous.com", "is_staff": False, "is_active": True,
                          "date_joined": "2018-08-28T19:05:45.653687Z"}

        self.add_page_in_use_mocks(responses)

        tag_json = {"results": []}

        responses.add(
            responses.GET,
            "http://testserver/ws/page_in_use_filter/AnonymousUser//campaigns/Campaign1/asset/Asset1//",
            json={"count": 0, "results": []},
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/asset_by_slug/Campaign1/Asset1/",
            json=asset_by_slug_response,
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/transcription/%s/" % (self.asset.id,),
            json=transcription_json,
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/tags/%s/" % (self.asset.id,),
            json=tag_json,
            status=200,
        )

        responses.add(
            responses.POST, "http://testserver/ws/transcription_create/", status=200
        )
        responses.add(responses.POST, "http://testserver/ws/tag_create/", status=200)

        responses.add(responses.PUT,
                      "http://testserver/ws/page_in_use_update/%s//campaigns/Campaign1/asset/Asset1//" %
                      (self.anon_user.id, ),
                      status=200)

        responses.add(
            responses.GET,
            "http:////testserver/ws/anonymous_user/",
            json=anonymous_json,
            status=200
        )

        tag_name = "Test tag 1"

        # Act
        # post as anonymous user without captcha data
        response = self.client.post(
            "/campaigns/Campaign1/asset/Asset1/",
            {"tx": "First Test Transcription", "tags": tag_name, "action": "Save"},
        )

        # Assert
        self.assertEqual(response.status_code, 200)

    @responses.activate
    def test_ConcordiaAssetView_get(self):
        """
        This unit test test the GET route /campaigns/<campaign>/asset/<Asset_name>/
        with already in use. Verify the updated_on time is updated on PageInUse
        :return:
        """
        asset_slug = "Asset1"

        # Arrange
        self.login_user()

        # create a campaign
        self.campaign = Campaign(
            title="TestCampaign",
            slug="Campaign1",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        # create an Asset
        self.asset = Asset(
            title="TestAsset",
            slug=asset_slug,
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        # add a Transcription object
        self.transcription = Transcription(
            asset=self.asset,
            user_id=self.user.id,
            text="Test transcription 1",
            status=Status.EDIT,
        )
        self.transcription.save()

        # mock REST responses

        asset_by_slug_response = {
            "id": self.asset.id,
            "title": "TestAsset",
            "slug": asset_slug,
            "description": "mss859430177",
            "media_url": "https://s3.us-east-2.amazonaws.com/chc-collections/test_s3/mss859430177/1.jpg",
            "media_type": MediaType.IMAGE,
            "campaign": {"slug": "Campaign1"},
            "project": None,
            "sequence": 1,
            "metadata": {"key": "val2"},
            "status": Status.EDIT,
        }

        transcription_json = {
            "asset": {
                "title": "",
                "slug": "",
                "description": "",
                "media_url": "",
                "media_type": None,
                "campaign": {
                    "slug": "",
                    "title": "",
                    "description": "",
                    "s3_storage": False,
                    "start_date": None,
                    "end_date": None,
                    "status": None,
                    "assets": [],
                },
                "project": None,
                "sequence": None,
                "metadata": None,
                "status": None,
            },
            "user_id": None,
            "text": "",
            "status": None,
        }

        tag_json = {"results": []}

        self.add_page_in_use_mocks(responses)

        responses.add(
            responses.PUT,
            "http://testserver/ws/page_in_use_update/%s//campaigns/Campaign1/asset/Asset1//" % (self.user.id, ),
            status=200)

        responses.add(
            responses.GET,
            "http://testserver/ws/page_in_use_user/%s//campaigns/Campaign1/asset/Asset1//" % (self.user.id, ),
            json={"user": self.user.id},
            status=200
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/asset_by_slug/Campaign1/Asset1/",
            json=asset_by_slug_response,
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/transcription/%s/" % (self.asset.id,),
            json=transcription_json,
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/tags/%s/" % (self.asset.id,),
            json=tag_json,
            status=200,
        )

        self.add_page_in_use_mocks(responses)

        url = "/campaigns/Campaign1/asset/Asset1/"

        # Act
        response = self.client.get(url)

        # Assert
        self.assertEqual(response.status_code, 200)

    @responses.activate
    def test_redirect_when_same_page_in_use(self):
        """
        Test the GET route for /campaigns/<campaign>/alternateasset/<Asset_name>/
        :return:
        """
        # Arrange
        self.login_user()

        # create a campaign
        self.campaign = Campaign(
            title="TestCampaign",
            slug="Campaign1",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        # create 2 Assets
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

        self.asset2 = Asset(
            title="TestAsset2",
            slug="Asset2",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset2.save()

        # Mock REST API calls

        asset_json = {
                "title": "TestAsset2",
                "slug": "Asset2",
                "description": "",
                "media_url": "",
                "media_type": None,
                "campaign": {
                    "slug": "",
                    "title": "",
                    "description": "",
                    "s3_storage": False,
                    "start_date": None,
                    "end_date": None,
                    "status": None,
                    "assets": [],
                },
                "project": None,
                "sequence": None,
                "metadata": None,
                "status": Status.EDIT,
            }

        responses.add(
            responses.GET,
            "http://testserver/ws/campaign_asset_random/%s/%s" % (self.campaign.slug, self.asset.slug,),
            json=asset_json,
            status=200,
        )

        # Act
        response = self.client.post(
            "/campaigns/alternateasset/",
            {"campaign": self.campaign.slug, "asset": self.asset.slug},
        )

        # Assert
        self.assertEqual(response.status_code, 200)

    @responses.activate
    def test_pageinuse_post(self):
        """
        Test the POST method on /campaigns/pageinuse/ route

        test that matching PageInUse entries with same page_url are deleted
        test that old entries in PageInUse table are removed
        :return:
        """

        # Arrange
        self.login_user()
        url = "foo.com/bar"

        user2 = User.objects.create(username="tester2", email="tester2@foo.com")
        user2.set_password("top_secret")
        user2.save()

        page1 = PageInUse(page_url=url, user=user2)
        page1.save()

        from datetime import datetime, timedelta

        time_threshold = datetime.now() - timedelta(minutes=20)

        # add two entries with old timestamps
        page2 = PageInUse(
            page_url="foo.com/blah",
            user=self.user,
            created_on=time_threshold,
            updated_on=time_threshold,
        )
        page2.save()

        page3 = PageInUse(
            page_url="bar.com/blah",
            user=self.user,
            created_on=time_threshold,
            updated_on=time_threshold,
        )
        page3.save()

        # Mock REST API
        user_json_val = {"id": self.user.id, "username": "anonymous",
                         "password": "pbkdf2_sha256$100000$6lht1V74YYXZ$fagq9FeSFlDfqqikuBRGMcxl1GaBvC7tIO7fiiAkReo=",
                         "first_name": "",
                         "last_name": "", "email": "anonymous@anonymous.com", "is_staff": False, "is_active": True,
                         "date_joined": "2018-08-28T19:05:45.653687Z"}

        responses.add(
            responses.GET,
            "http://testserver/ws/user/%s/" % (self.user.username, ),
            json=user_json_val,
            status=200,
        )

        responses.add(responses.PUT,
                      "http://testserver/ws/page_in_use_update/%s/%s/" % (self.user.id, url, ),
                      status=200)

                # Act
        response = self.client.post(
            "/campaigns/pageinuse/", {"page_url": url, "user": self.user}
        )

        # Assert
        self.assertEqual(response.status_code, 200)

    @responses.activate
    def test_ConcordiaProjectView_get(self):
        """
        Test GET on route /campaigns/<slug-value> (campaign)
        :return:
        """

        # Arrange

        # add an item to Campaign
        self.campaign = Campaign(
            title="TextCampaign",
            slug="test-slug2",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        self.project = Project(
            title="TextCampaign project",
            slug="test-slug2-proj",
            metadata={"key": "val1"},
            status=Status.EDIT,
            campaign=self.campaign,
        )
        self.project.save()

        self.project1 = Project(
            title="TextCampaign project 1",
            slug="test-slug2-proj1",
            metadata={"key": "val1"},
            status=Status.EDIT,
            campaign=self.campaign,
        )
        self.project1.save()

        # mock REST requests

        campaign_json = {
            "id": self.campaign.id,
            "slug": "test-slug2",
            "title": "TextCampaign",
            "description": "Campaign Description",
            "s3_storage": True,
            "start_date": None,
            "end_date": None,
            "status": Status.EDIT,
            "assets": [],
        }

        responses.add(
            responses.GET,
            "http://testserver/ws/campaign/test-slug2/",
            json=campaign_json,
            status=200,
        )

        # Act
        response = self.client.get("/campaigns/test-slug2/test-slug2-proj1/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="transcriptions/project.html")

    @responses.activate
    def test_ConcordiaProjectView_get_page2(self):
        """
        Test GET on route /campaigns/<slug-value>/ (campaign) on page 2
        :return:
        """

        # Arrange

        # add an item to Campaign
        self.campaign = Campaign(
            title="TextCampaign",
            slug="test-slug2",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        self.project = Project(
            title="TextCampaign project",
            slug="test-slug2-proj",
            metadata={"key": "val1"},
            status=Status.EDIT,
            campaign=self.campaign,
        )
        self.project.save()

        self.project1 = Project(
            title="TextCampaign project 1",
            slug="test-slug2-proj1",
            metadata={"key": "val1"},
            status=Status.EDIT,
            campaign=self.campaign,
        )
        self.project1.save()

        # mock REST requests

        campaign_json = {
            "id": self.campaign.id,
            "slug": "test-slug2",
            "title": "TextCampaign",
            "description": "Campaign Description",
            "s3_storage": True,
            "start_date": None,
            "end_date": None,
            "status": Status.EDIT,
            "assets": [],
        }

        responses.add(
            responses.GET,
            "http://testserver/ws/campaign/test-slug2/",
            json=campaign_json,
            status=200,
        )

        # Act
        response = self.client.get(
            "/campaigns/test-slug2/test-slug2-proj1/", {"page": 2}
        )

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="transcriptions/project.html")

    def test_FilterCampaigns_get(self):
        """Test list of filer campaign get API"""

        # Arrange
        self.campaign = Campaign(
            title="TextCampaign",
            slug="slug1",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        self.campaign = Campaign(
            title="Text Campaign",
            slug="slug2",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        # Act
        response = self.client.get("/filter/campaigns/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)
        self.assertEqual(response.json()[0], "slug1")
        self.assertEqual(response.json()[1], "slug2")

    def test_FilterCampaignsWithParams_get(self):
        """Test list of filer campaign get API"""

        # Arrange
        self.campaign = Campaign(
            title="TextCampaign",
            slug="slug1",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        self.campaign = Campaign(
            title="Text Campaign",
            slug="slug2",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        # Act
        response = self.client.get("/filter/campaigns/?name=sl")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)
        self.assertEqual(response.json()[0], "slug1")
        self.assertEqual(response.json()[1], "slug2")

    def test_FilterCampaignsEmpty_get(self):
        """Test list of filer campaign get API"""

        # Arrange, to test empty filter campaigns. No need of arranging data

        # Act
        response = self.client.get("/filter/campaigns/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 0)

    def test_PublishCampaignView(self):
        """Test for updating status of a campaign"""

        # Arrange
        self.campaign = Campaign(
            title="TextCampaign",
            slug="slug1",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        self.project = Project(
            title="TextCampaign project",
            slug="test-slug2-proj",
            metadata={"key": "val1"},
            status=Status.EDIT,
            campaign=self.campaign,
        )
        self.project.save()

        self.project1 = Project(
            title="TextCampaign project 1",
            slug="test-slug2-proj1",
            metadata={"key": "val1"},
            status=Status.EDIT,
            campaign=self.campaign,
        )
        self.project1.save()

        # Act
        response = self.client.get("/campaigns/publish/campaign/slug1/true/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], True)

    def test_UnpublishCampaignView(self):
        """Test for updating status of a campaign"""

        # Arrange
        self.campaign = Campaign(
            title="TextCampaign",
            slug="slug1",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
            is_publish=True,
        )
        self.campaign.save()

        self.project = Project(
            title="TextCampaign project",
            slug="test-slug2-proj",
            metadata={"key": "val1"},
            status=Status.EDIT,
            campaign=self.campaign,
            is_publish=True,
        )
        self.project.save()

        self.project1 = Project(
            title="TextCampaign project 1",
            slug="test-slug2-proj1",
            metadata={"key": "val1"},
            status=Status.EDIT,
            campaign=self.campaign,
            is_publish=True,
        )
        self.project1.save()

        # Act
        response = self.client.get("/campaigns/publish/campaign/slug1/false/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], False)

    def test_PublishProjectView(self):
        """Test for updating status of a project"""

        # Arrange
        self.campaign = Campaign(
            title="TextCampaign",
            slug="slug1",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        self.project = Project(
            title="TextCampaign project",
            slug="test-slug2-proj",
            metadata={"key": "val1"},
            status=Status.EDIT,
            campaign=self.campaign,
        )
        self.project.save()

        self.project1 = Project(
            title="TextCampaign project1",
            slug="test-slug2-proj1",
            metadata={"key": "val1"},
            status=Status.EDIT,
            campaign=self.campaign,
        )
        self.project1.save()

        # Act
        response = self.client.get(
            "/campaigns/publish/project/slug1/test-slug2-proj/true/"
        )

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], True)

    def test_UnpublishProjectView(self):
        """Test for updating status of a project"""

        # Arrange
        self.campaign = Campaign(
            title="TextCampaign",
            slug="slug1",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
            is_publish=True,
        )
        self.campaign.save()

        self.project = Project(
            title="TextCampaign project",
            slug="test-slug2-proj",
            metadata={"key": "val1"},
            status=Status.EDIT,
            campaign=self.campaign,
            is_publish=True,
        )
        self.project.save()

        self.project1 = Project(
            title="TextCampaign project1",
            slug="test-slug2-proj1",
            metadata={"key": "val1"},
            status=Status.EDIT,
            campaign=self.campaign,
            is_publish=True,
        )
        self.project1.save()

        # Act
        response = self.client.get(
            "/campaigns/publish/project/slug1/test-slug2-proj/false/"
        )

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], False)
