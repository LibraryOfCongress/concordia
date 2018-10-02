# TODO: Add correct copyright header

import logging
import re
import tempfile

import responses
from captcha.models import CaptchaStore
from django.test import TestCase
from PIL import Image

from concordia.models import (
    Asset,
    Campaign,
    Item,
    MediaType,
    PageInUse,
    Project,
    Status,
    Transcription,
    User,
    UserProfile,
)

logging.disable(logging.CRITICAL)


class ViewTest_Concordia(TestCase):
    """
    This class contains the unit tests for the view in the concordia app.

    Make sure the postgresql db is available. Run docker-compose up db
    """

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
            "http://testserver/ws/page_in_use_count/%s//campaigns/Campaign1/asset/Asset1//"
            % (self.user.id if hasattr(self, "user") else self.anon_user.id,),
            json={"page_in_use": False},
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/page_in_use_user/%s//campaigns/Campaign1/asset/Asset1//"
            % (self.user.id if hasattr(self, "user") else self.anon_user.id,),
            json={"user": self.user.id if hasattr(self, "user") else self.anon_user.id},
            status=200,
        )

    def test_login_with_email(self):
        """
        Test the login is successful with email
        :return:
        """

        user = User.objects.create(username="etester", email="etester@foo.com")
        user.set_password("top_secret")
        user.save()

        user = self.client.login(username="etester@foo.com", password="top_secret")

        self.assertTrue(user)

    def test_AccountProfileView_get(self):
        """
        Test the http GET on route account/profile
        :return:
        """

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

        response = self.client.get("/account/profile/")

        # validate the web page has the "tester" and "tester@foo.com" as values
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="profile.html")

    def test_AccountProfileView_post(self):
        """
        This unit test tests the post entry for the route account/profile
        :param self:
        :return:
        """

        test_email = "tester@foo.com"

        self.login_user()

        response = self.client.post(
            "/account/profile/",
            {
                "email": test_email,
                "username": "tester",
                "password1": "!Abc12345",
                "password2": "!Abc12345",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/account/profile/")

        # Verify the User was correctly updated
        updated_user = User.objects.get(email=test_email)
        self.assertEqual(updated_user.email, test_email)

    def test_AccountProfileView_post_invalid_form(self):
        """
        This unit test tests the post entry for the route account/profile but submits an invalid form
        :param self:
        :return:
        """

        self.login_user()

        response = self.client.post("/account/profile/", {"first_name": "Jimmy"})

        self.assertEqual(response.status_code, 302)

        # Verify the User was not changed
        updated_user = User.objects.get(id=self.user.id)
        self.assertEqual(updated_user.first_name, "")

    def test_AccountProfileView_post_new_password(self):
        """
        This unit test tests the post entry for the route account/profile with new password
        :param self:
        :return:
        """

        self.login_user()

        test_email = "tester@foo.com"

        response = self.client.post(
            "/account/profile/",
            {
                "email": test_email,
                "username": "tester",
                "password1": "aBc12345!",
                "password2": "aBc12345!",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/account/profile/")

        # Verify the User was correctly updated
        updated_user = User.objects.get(email=test_email)
        self.assertEqual(updated_user.email, test_email)

        # logout and login with new password
        self.client.logout()
        login2 = self.client.login(username="tester", password="aBc12345!")

        self.assertTrue(login2)

    def test_concordiaView(self):
        """
        Test the GET method for route /campaigns
        :return:
        """

        response = self.client.get("/campaigns/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="transcriptions/campaigns.html")

    @responses.activate
    def test_concordiaCampaignView_get(self):
        """
        Test GET on route /campaigns/<slug-value> (campaign)
        :return:
        """

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

        response = self.client.get("/campaigns/test-slug2/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/campaign_detail.html"
        )

    @responses.activate
    def test_concordiaCampaignView_get_page2(self):
        """
        Test GET on route /campaigns/<slug-value>/ (campaign) on page 2
        :return:
        """

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

        response = self.client.get("/campaigns/test-slug2/", {"page": 2})

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/campaign_detail.html"
        )

    @responses.activate
    def test_ConcordiaItemView_get(self):
        """
        Test GET on route /campaigns/<campaign-slug>/<project-slug>/<item-slug>
        :return:
        """

        # add an item to Campaign
        self.campaign = Campaign(
            title="TextCampaign", slug="test-slug", status=Status.EDIT
        )
        self.campaign.save()

        self.project = Project(
            title="TestProject", slug="project-slug", campaign=self.campaign
        )

        self.project.save()

        self.item = Item(
            title="item-slug",
            slug="item-slug",
            item_id="item-slug",
            published=True,
            campaign=self.campaign,
            project=self.project,
        )

        self.item.save()

        # mock REST requests

        item_json = {
            "slug": self.item.slug,
            "title": self.item.title,
            "description": "Item Description",
            "assets": [],
            "published": True,
            "campaign": self.campaign.id,
            "project": self.project.id,
        }

        responses.add(
            responses.GET,
            "http://testserver/ws/item_by_id/item-slug",
            json=item_json,
            status=200,
        )

        response = self.client.get(
            "/campaigns/test-slug/project-slug/item-slug", follow=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="transcriptions/item.html")

    def test_ExportCampaignView_get(self):
        """
        Test GET route /campaigns/export/<slug-value>/ (campaign)
        :return:
        """

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

        response = self.client.get("/campaigns/exportCSV/slug2/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            str(response.content),
            "b'Campaign,Title,Description,MediaUrl,Transcription,Tags\\r\\n"
            "TextCampaign,TestAsset,Asset Description,"
            "http://www.foo.com/1/2/3,,\\r\\n'",
        )

    @responses.activate
    def test_ConcordiaAssetView_post_anonymous_happy_path(self):
        """
        This unit test test the POST route /campaigns/<campaign>/asset/<Asset_name>/
        for an anonymous user. This user should not be able to tag
        :return:
        """

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
        self.anon_user = User.objects.create(
            username="anonymous", email="tester@foo.com"
        )
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

        anonymous_json = {
            "id": self.anon_user.id,
            "username": "anonymous",
            "password": "pbkdf2_sha256$100000$6lht1V74YYXZ$fagq9FeSFlDfqqikuBRGMcxl1GaBvC7tIO7fiiAkReo=",
            "first_name": "",
            "last_name": "",
            "email": "anonymous@anonymous.com",
            "is_staff": False,
            "is_active": True,
            "date_joined": "2018-08-28T19:05:45.653687Z",
        }

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

        responses.add(
            responses.PUT,
            "http://testserver/ws/page_in_use_update/%s//campaigns/Campaign1/asset/Asset1//"
            % (self.anon_user.id,),
            status=200,
        )

        responses.add(
            responses.GET,
            "http:////testserver/ws/anonymous_user/",
            json=anonymous_json,
            status=200,
        )

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
        self.anon_user = User.objects.create(
            username="anonymous", email="tester@foo.com"
        )
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

        anonymous_json = {
            "id": self.anon_user.id,
            "username": "anonymous",
            "password": "pbkdf2_sha256$100000$6lht1V74YYXZ$fagq9FeSFlDfqqikuBRGMcxl1GaBvC7tIO7fiiAkReo=",
            "first_name": "",
            "last_name": "",
            "email": "anonymous@anonymous.com",
            "is_staff": False,
            "is_active": True,
            "date_joined": "2018-08-28T19:05:45.653687Z",
        }

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

        responses.add(
            responses.PUT,
            "http://testserver/ws/page_in_use_update/%s//campaigns/Campaign1/asset/Asset1//"
            % (self.anon_user.id,),
            status=200,
        )

        responses.add(
            responses.GET,
            "http:////testserver/ws/anonymous_user/",
            json=anonymous_json,
            status=200,
        )

        tag_name = "Test tag 1"

        # post as anonymous user without captcha data
        response = self.client.post(
            "/campaigns/Campaign1/asset/Asset1/",
            {"tx": "First Test Transcription", "tags": tag_name, "action": "Save"},
        )

        self.assertEqual(response.status_code, 200)

    @responses.activate
    def test_ConcordiaAssetView_get(self):
        """
        This unit test test the GET route /campaigns/<campaign>/asset/<Asset_name>/
        with already in use. Verify the updated_on time is updated on PageInUse
        :return:
        """
        asset_slug = "Asset1"

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
            "http://testserver/ws/page_in_use_update/%s//campaigns/Campaign1/asset/Asset1//"
            % (self.user.id,),
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/page_in_use_user/%s//campaigns/Campaign1/asset/Asset1//"
            % (self.user.id,),
            json={"user": self.user.id},
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

        self.add_page_in_use_mocks(responses)

        url = "/campaigns/Campaign1/asset/Asset1/"

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

    @responses.activate
    def test_redirect_when_same_page_in_use(self):
        """
        Test the GET route for /campaigns/<campaign>/alternateasset/<Asset_name>/
        :return:
        """

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
            "http://testserver/ws/campaign_asset_random/%s/%s"
            % (self.campaign.slug, self.asset.slug),
            json=asset_json,
            status=200,
        )

        response = self.client.post(
            "/campaigns/alternateasset/",
            {"campaign": self.campaign.slug, "asset": self.asset.slug},
        )

        self.assertEqual(response.status_code, 200)

    @responses.activate
    def test_pageinuse_post(self):
        """
        Test the POST method on /campaigns/pageinuse/ route

        test that matching PageInUse entries with same page_url are deleted
        test that old entries in PageInUse table are removed
        :return:
        """

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
        user_json_val = {
            "id": self.user.id,
            "username": "anonymous",
            "password": "pbkdf2_sha256$100000$6lht1V74YYXZ$fagq9FeSFlDfqqikuBRGMcxl1GaBvC7tIO7fiiAkReo=",
            "first_name": "",
            "last_name": "",
            "email": "anonymous@anonymous.com",
            "is_staff": False,
            "is_active": True,
            "date_joined": "2018-08-28T19:05:45.653687Z",
        }

        responses.add(
            responses.GET,
            "http://testserver/ws/user/%s/" % (self.user.username,),
            json=user_json_val,
            status=200,
        )

        responses.add(
            responses.PUT,
            "http://testserver/ws/page_in_use_update/%s/%s/" % (self.user.id, url),
            status=200,
        )

        response = self.client.post(
            "/campaigns/pageinuse/", {"page_url": url, "user": self.user}
        )

        self.assertEqual(response.status_code, 200)

    @responses.activate
    def test_ConcordiaProjectView_get(self):
        """
        Test GET on route /campaigns/<slug-value> (campaign)
        :return:
        """

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

        response = self.client.get("/campaigns/test-slug2/test-slug2-proj1/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="transcriptions/project.html")

    @responses.activate
    def test_ConcordiaProjectView_get_page2(self):
        """
        Test GET on route /campaigns/<slug-value>/ (campaign) on page 2
        :return:
        """

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

        response = self.client.get(
            "/campaigns/test-slug2/test-slug2-proj1/", {"page": 2}
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="transcriptions/project.html")

    def test_PublishCampaignView(self):
        """Test for updating status of a campaign"""

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

        response = self.client.get("/campaigns/publish/campaign/slug1/true/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], True)
