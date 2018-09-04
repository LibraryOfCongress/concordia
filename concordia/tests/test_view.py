# TODO: Add correct copyright header

import logging
import re
import tempfile
import time
from unittest.mock import Mock, patch

import views
from captcha.models import CaptchaStore
from django.test import Client, TestCase
from PIL import Image

from concordia.models import (Asset, Campaign, MediaType, PageInUse, Status,
                              Project, Tag, Transcription, User,
                              UserAssetTagCollection, UserProfile)

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

    def test_get_anonymous_user(self):
        """
        Test getting the anonymous user. Test the naonymous user does exist, the call
        get_anonymous_user, make anonymous is created
        :return:
        """

        # Arrange
        anon_user1 = User.objects.filter(username="anonymous").first()

        # Act
        anon_user_id = views.get_anonymous_user()
        anon_user_from_db = User.objects.filter(username="anonymous").first()

        # Assert
        self.assertEqual(anon_user1, None)
        self.assertEqual(anon_user_id, anon_user_from_db.id)

    def test_get_anonymous_user_already_exists(self):
        """
        Test getting the anonymous user when it already exists.
        :return:
        """

        # Arrange
        anon_user = User.objects.create_user(
            username="anonymous",
            email="anonymous@anonymous.com",
            password="concanonymous",
        )

        # Act
        anon_user_id = views.get_anonymous_user()

        # Assert
        self.assertEqual(anon_user_id, anon_user.id)

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

    def test_AccountProfileView_get(self):
        """
        Test the http GET on route account/profile
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
        response = self.client.get("/account/profile/")

        # Assert

        # validate the web page has the "tester" and "tester@foo.com" as values
        self.assertTrue('value="tester"' in str(response.content))
        self.assertTrue('value="tester@foo.com"' in str(response.content))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="profile.html")

    def test_AccountProfileView_post(self):
        """
        This unit test tests the post entry for the route account/profile
        :param self:
        :return:
        """

        test_email = "tester@foo.com"

        # Arrange
        self.login_user()

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

    def test_AccountProfileView_post_invalid_form(self):
        """
        This unit test tests the post entry for the route account/profile but submits an invalid form
        :param self:
        :return:
        """

        # Arrange
        self.login_user()

        # Act
        response = self.client.post("/account/profile/", {"first_name": "Jimmy"})

        # Assert
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

        # Arrange
        self.login_user()

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

    def test_AccountProfileView_post_with_image(self):
        """
        This unit test tests the post entry for the
        route account/profile with new image file
        :param self:
        :return:
        """

        # Arrange
        self.login_user()

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
        Test the GET method for route /transcribe
        :return:
        """
        # Arrange

        mock_requests.get.return_value.status_code = 200
        mock_requests.get.return_value.json.return_value = {
            "concordia_data": "abc123456"
        }

        # Act
        response = self.client.get("/transcribe/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="transcriptions/home.html")

    def test_concordiaCampaignView_get(self):
        """
        Test GET on route /transcribe/<slug-value> (campaign)
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

        # Act
        response = self.client.get("/transcribe/test-slug2/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="transcriptions/project.html")

    def test_concordiaCampaignView_get_page2(self):
        """
        Test GET on route /transcribe/<slug-value>/ (campaign) on page 2
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

        # Act
        response = self.client.get("/transcribe/test-slug2/", {"page": 2})

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="transcriptions/project.html")

    def test_ExportCampaignView_get(self):
        """
        Test GET route /transcribe/export/<slug-value>/ (campaign)
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
        response = self.client.get("/transcribe/exportCSV/slug2/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            str(response.content),
            "b'Campaign,Title,Description,MediaUrl,Transcription,Tags\\r\\n"
            "TextCampaign,TestAsset,Asset Description,"
            "http://www.foo.com/1/2/3,,\\r\\n'",
        )

    @patch("concordia.views.requests")
    def test_DeleteCampaign_get(self, mock_requests):
        """
        Test GET route /transcribe/delete/<slug-value>/ (campaign)
        :return:
        """

        # Arrange
        mock_requests.get.return_value.status_code = 200
        mock_requests.get.return_value.json.return_value = {
            "concordia_data": "abc123456"
        }

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

        # Act

        response = self.client.get("/transcribe/delete/test-slug2", follow=True)

        # Assert
        self.assertEqual(response.status_code, 200)

        # verify the campaign is not in db
        campaign2 = Campaign.objects.all()
        self.assertEqual(len(campaign2), 0)

    @patch("concordia.views.requests")
    def test_DeleteAsset_get(self, mock_requests):
        """
        Test GET route /transcribe/delete/asset/<slug-value>/ (asset)
        :return:
        """

        # Arrange
        mock_requests.get.return_value.status_code = 200
        mock_requests.get.return_value.json.return_value = {
            "concordia_data": "abc123456"
        }

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

        # Act

        response = self.client.get(
            "/transcribe/test-campaign-slug/delete/asset/test-asset-slug1/",
            follow=True,
        )

        # Assert
        self.assertEqual(response.status_code, 200)

        campaign2 = Campaign.objects.get(slug="test-campaign-slug")
        all_assets = Asset.objects.filter(campaign=campaign2)
        hided_assets = Asset.objects.filter(
            campaign=campaign2, status=Status.INACTIVE
        )
        self.assertEqual(len(all_assets), 2)
        self.assertEqual(len(hided_assets), 1)

    def test_ConcordiaAssetView_post(self):
        """
        This unit test test the POST route /transcribe/<campaign>/asset/<Asset_name>/
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

        # add a Transcription object
        self.transcription = Transcription(
            asset=self.asset,
            user_id=self.user.id,
            text="Test transcription 1",
            status=Status.EDIT,
        )
        self.transcription.save()

        tag_name = "Test tag 1"

        # Act
        response = self.client.post(
            "/transcribe/Campaign1/asset/Asset1/",
            {"tx": "First Test Transcription", "tags": tag_name, "action": "Save"},
        )

        # Assert
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/transcribe/Campaign1/asset/Asset1/")

        # Verify the new transcription and tag are in the db
        transcription = Transcription.objects.filter(
            text="First Test Transcription", asset=self.asset
        )
        self.assertEqual(len(transcription), 1)

        tags = UserAssetTagCollection.objects.filter(
            asset=self.asset, user_id=self.user.id
        )
        if tags:
            separate_tags = tags[0].tags.all()

        self.assertEqual(len(tags), 1)
        self.assertEqual(separate_tags[0].name, tag_name)

    def test_ConcordiaAssetView_post_contact_community_manager(self):
        """
        This unit test test the POST route /transcribe/<campaign>/asset/<Asset_name>/
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

        # create an Asset
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

        # create anonymous user
        anon_user = User.objects.create(username="anonymous", email="tester@foo.com")
        anon_user.set_password("blah_anonymous!")
        anon_user.save()

        # add a Transcription object
        self.transcription = Transcription(
            asset=self.asset,
            user_id=anon_user.id,
            text="Test transcription 1",
            status=Status.EDIT,
        )
        self.transcription.save()

        tag_name = "Test tag 1"

        # Act
        response = self.client.get("/transcribe/Campaign1/asset/Asset1/")
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            "/transcribe/Campaign1/asset/Asset1/",
            {"tx": "", "tags": "", "action": "Contact Manager"},
        )

        # Assert
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/contact/?pre_populate=true")

    def test_ConcordiaAssetView_post_anonymous_happy_path(self):
        """
        This unit test test the POST route /transcribe/<campaign>/asset/<Asset_name>/
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

        # create anonymous user
        anon_user = User.objects.create(username="anonymous", email="tester@foo.com")
        anon_user.set_password("blah_anonymous!")
        anon_user.save()

        # add a Transcription object
        self.transcription = Transcription(
            asset=self.asset,
            user_id=anon_user.id,
            text="Test transcription 1",
            status=Status.EDIT,
        )
        self.transcription.save()

        tag_name = "Test tag 1"

        # Act
        response = self.client.get("/transcribe/Campaign1/asset/Asset1/")
        self.assertEqual(response.status_code, 200)
        hash_ = re.findall(r'value="([0-9a-f]+)"', str(response.content))[0]
        captcha_response = CaptchaStore.objects.get(hashkey=hash_).response

        response = self.client.post(
            "/transcribe/Campaign1/asset/Asset1/",
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
        self.assertEqual(response.url, "/transcribe/Campaign1/asset/Asset1/")

        # Verify the new transcription in the db
        transcription = Transcription.objects.filter(
            text="First Test Transcription 1", asset=self.asset
        )
        self.assertEqual(len(transcription), 1)

        tags = UserAssetTagCollection.objects.filter(
            asset=self.asset, user_id=anon_user.id
        )

        # Tag is not in db,  as anonymous user can't tag
        self.assertEqual(len(tags), 0)

    def test_ConcordiaAssetView_post_anonymous_invalid_captcha(self):
        """
        This unit test test the POST route /transcribe/<campaign>/asset/<Asset_name>/
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

        # create anonymous user
        anon_user = User.objects.create(username="anonymous", email="tester@foo.com")
        anon_user.set_password("blah_anonymous!")
        anon_user.save()

        # add a Transcription object
        self.transcription = Transcription(
            asset=self.asset,
            user_id=anon_user.id,
            text="Test transcription 1",
            status=Status.EDIT,
        )
        self.transcription.save()

        tag_name = "Test tag 1"

        # Act
        # post as anonymous user without captcha data
        response = self.client.post(
            "/transcribe/Campaign1/asset/Asset1/",
            {"tx": "First Test Transcription", "tags": tag_name, "action": "Save"},
        )

        # Assert
        self.assertEqual(response.status_code, 200)

        # Verify the new transcription are not in db
        transcription = Transcription.objects.filter(
            text="First Test Transcription", asset=self.asset
        )
        self.assertEqual(len(transcription), 0)

    def test_ConcordiaAssetView_get(self):
        """
        This unit test test the GET route /transcribe/<campaign>/asset/<Asset_name>/
        with already in use. Verify the updated_on time is updated on PageInUse
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

        url = "/transcribe/Campaign1/asset/Asset1/"

        # Act
        response = self.client.get(url)

        # Assert
        self.assertEqual(response.status_code, 200)

        # get PageInUse value
        page_in_use = PageInUse.objects.get(page_url=url)

        # sleep so update time can be tested against original time
        time.sleep(2)

        # Act
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # get PageInUse value
        page_in_use2 = PageInUse.objects.get(page_url=url)
        self.assertNotEqual(page_in_use.updated_on, page_in_use2.updated_on)
        self.assertEqual(page_in_use.created_on, page_in_use2.created_on)

    def test_page_in_use_same_user(self):
        """
        Test the ConcordiaAssetView page_in_view returns False when PageInUse entry exists for same user
        :return:
        """
        # Arrange
        self.login_user()

        # Add values to database
        self.campaign = Campaign(
            title="TestCampaign",
            slug="TestCampaign",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        # create an Asset
        self.asset = Asset(
            title="TestAsset",
            slug="TestAsset",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        in_use_url = "/transcribe/%s/asset/%s/" % (
            self.asset.campaign.slug,
            self.asset.slug,
        )

        PageInUse.objects.create(page_url=in_use_url, user=self.user)

        # Act
        concordia_asset_view = views.ConcordiaAssetView()

        results = concordia_asset_view.check_page_in_use(in_use_url, self.user)

        # Assert
        self.assertEqual(results, False)

    def test_page_in_use_different_user(self):
        """
        Test the ConcordiaAssetView page_in_view returns True when PageInUse entry exists with different user
        :return:
        """
        # Arrange
        self.login_user()

        user2 = User.objects.create(username="tester2", email="tester2@foo.com")
        user2.set_password("top_secret2")
        user2.save()

        # Add values to database
        self.campaign = Campaign(
            title="TestCampaign",
            slug="TestCampaign",
            description="Campaign Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.campaign.save()

        # create an Asset
        self.asset = Asset(
            title="TestAsset",
            slug="TestAsset",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            campaign=self.campaign,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        in_use_url = "/transcribe/%s/asset/%s/" % (
            self.asset.campaign.slug,
            self.asset.slug,
        )

        PageInUse.objects.create(page_url=in_use_url, user=user2)

        # Act
        concordia_asset_view = views.ConcordiaAssetView()

        results = concordia_asset_view.check_page_in_use(in_use_url, self.user)

        # Assert
        self.assertEqual(results, True)

    def test_redirect_when_same_page_in_use(self):
        """
        Test the GET route for /transcribe/<campaign>/alternateasset/<Asset_name>/
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

        # Act
        response = self.client.post(
            "/transcribe/alternateasset/",
            {"campaign": self.campaign.slug, "asset": self.asset.slug},
        )

        # Assert
        self.assertEqual(response.status_code, 200)

        # only 2 assets in campaign, this response should be for the other asset
        self.assertEqual(
            str(response.content, "utf-8"), "/transcribe/Campaign1/asset/Asset2/"
        )

    def test_pageinuse_post(self):
        """
        Test the POST method on /transcribe/pageinuse/ route

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

        # Act
        response = self.client.post(
            "/transcribe/pageinuse/", {"page_url": url, "user": self.user}
        )

        # Assert
        self.assertEqual(response.status_code, 200)

        pages = PageInUse.objects.all()
        self.assertEqual(len(pages), 1)
        self.assertNotEqual(page1.created_on, pages[0].created_on)

    def test_pageinuse_multiple_same_entries_in_pageinuse_post(self):
        """
        Test the POST method on /transcribe/pageinuse/ route
        Create an additional entry in PageInUse, verify 1 different entry in PageInUse after call
        :return:
        """

        # Arrange
        self.login_user()

        # Act
        response = self.client.post(
            "/transcribe/pageinuse/", {"page_url": "foo.com/bar", "user": self.user}
        )

        # Assert
        self.assertEqual(response.status_code, 200)

    def test_get_anonymous_user(self):
        """
        Test retrieving the anonymous user
        :return:
        """

        # Arrange
        anon_id = views.get_anonymous_user()

        # Act
        anon_user = User.objects.get(id=anon_id)

        # Assert
        self.assertEqual(anon_user.id, anon_id)

    def test_get_anonymous_user_obj(self):
        """
        Test retrieving the anonymous user object
        :return:
        """

        # Arrange
        anon_obj = views.get_anonymous_user(False)

        # Act
        anon_user = User.objects.get(username=anon_obj.username)

        # Assert
        self.assertEqual(anon_user.id, anon_obj.id)

    def test_ConcordiaProjectView_get(self):
        """
        Test GET on route /transcribe/<slug-value> (campaign)
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
            title="TextCampaign sub campaign",
            slug="test-slug2-proj",
            metadata={"key": "val1"},
            status=Status.EDIT,
            campaign=self.campaign,
        )
        self.project.save()

        self.project1 = Project(
            title="TextCampaign sub collection1",
            slug="test-slug2-proj1",
            metadata={"key": "val1"},
            status=Status.EDIT,
            campaign=self.campaign,
        )
        self.project1.save()

        # Act
        response = self.client.get("/transcribe/test-slug2/test-slug2-proj1/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/campaign.html"
        )

    def test_ConcordiaProjectView_get_page2(self):
        """
        Test GET on route /transcribe/<slug-value>/ (campaign) on page 2
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
            title="TextCampaign sub campaign",
            slug="test-slug2-proj",
            metadata={"key": "val1"},
            status=Status.EDIT,
            campaign=self.campaign,
        )
        self.project.save()

        self.project1 = Project(
            title="TextCampaign sub collection1",
            slug="test-slug2-proj1",
            metadata={"key": "val1"},
            status=Status.EDIT,
            campaign=self.campaign,
        )
        self.project1.save()

        # Act
        response = self.client.get(
            "/transcribe/test-slug2/test-slug2-proj1/", {"page": 2}
        )

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/campaign.html"
        )

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
            title="TextCampaign sub campaign",
            slug="test-slug2-proj",
            metadata={"key": "val1"},
            status=Status.EDIT,
            campaign=self.campaign,
        )
        self.project.save()

        self.project1 = Project(
            title="TextCampaign sub collection1",
            slug="test-slug2-proj1",
            metadata={"key": "val1"},
            status=Status.EDIT,
            campaign=self.campaign,
        )
        self.project1.save()

        # Act
        response = self.client.get("/transcribe/publish/campaign/slug1/true/")

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
            title="TextCampaign sub campaign",
            slug="test-slug2-proj",
            metadata={"key": "val1"},
            status=Status.EDIT,
            campaign=self.campaign,
            is_publish=True,
        )
        self.project.save()

        self.project1 = Project(
            title="TextCampaign sub collection1",
            slug="test-slug2-proj1",
            metadata={"key": "val1"},
            status=Status.EDIT,
            campaign=self.campaign,
            is_publish=True,
        )
        self.project1.save()

        # Act
        response = self.client.get("/transcribe/publish/campaign/slug1/false/")

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
            title="TextCampaign sub campaign",
            slug="test-slug2-proj",
            metadata={"key": "val1"},
            status=Status.EDIT,
            campaign=self.campaign,
        )
        self.project.save()

        self.project1 = Project(
            title="TextCampaign sub collection1",
            slug="test-slug2-proj1",
            metadata={"key": "val1"},
            status=Status.EDIT,
            campaign=self.campaign,
        )
        self.project1.save()

        # Act
        response = self.client.get(
            "/transcribe/publish/project/slug1/test-slug2-proj/true/"
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
            title="TextCampaign sub campaign",
            slug="test-slug2-proj",
            metadata={"key": "val1"},
            status=Status.EDIT,
            campaign=self.campaign,
            is_publish=True,
        )
        self.project.save()

        self.project1 = Project(
            title="TextCampaign sub collection1",
            slug="test-slug2-proj1",
            metadata={"key": "val1"},
            status=Status.EDIT,
            campaign=self.campaign,
            is_publish=True,
        )
        self.project1.save()

        # Act
        response = self.client.get(
            "/transcribe/publish/project/slug1/test-slug2-proj/false/"
        )

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], False)
