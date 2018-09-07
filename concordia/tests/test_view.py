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

from concordia.models import (Asset, Collection, MediaType, PageInUse, Status,
                              Subcollection, Tag, Transcription, User,
                              UserAssetTagCollection, UserProfile)

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
            "http://testserver/ws/page_in_use_filter/tester//transcribe/Collection1/asset/Asset1//",
            json={"count": 0, "results": []},
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/page_in_use_count/%s//transcribe/Collection1/asset/Asset1//" %
            (self.user.id if hasattr(self, "user") else self.anon_user.id,),
            json={"page_in_use": False},
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/page_in_use_user/%s//transcribe/Collection1/asset/Asset1//" %
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

        # create a collection
        self.collection = Collection(
            title="TextCollection",
            slug="www.foo.com/slug2",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        # create an Asset
        self.asset = Asset(
            title="TestAsset",
            slug="www.foo.com/slug1",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            collection=self.collection,
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
        self.assertTrue('value="tester"' in str(response.content))
        self.assertTrue('value="tester@foo.com"' in str(response.content))
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

    @responses.activate
    def test_concordiaCollectionView_get(self):
        """
        Test GET on route /transcribe/<slug-value> (collection)
        :return:
        """

        # Arrange

        # add an item to Collection
        self.collection = Collection(
            title="TextCollection",
            slug="test-slug2",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        # mock REST requests

        collection_json = {
            "id": self.collection.id,
            "slug": "test-slug2",
            "title": "TextCollection",
            "description": "Collection Description",
            "s3_storage": True,
            "start_date": None,
            "end_date": None,
            "status": Status.EDIT,
            "assets": [],
            "subcollections": [],
        }

        responses.add(
            responses.GET,
            "http://testserver/ws/collection/test-slug2/",
            json=collection_json,
            status=200,
        )

        # Act
        response = self.client.get("/transcribe/test-slug2/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="transcriptions/project.html")

    @responses.activate
    def test_concordiaCollectionView_get_page2(self):
        """
        Test GET on route /transcribe/<slug-value>/ (collection) on page 2
        :return:
        """

        # Arrange

        # add an item to Collection
        self.collection = Collection(
            title="TextCollection",
            slug="test-slug2",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        # mock REST requests

        collection_json = {
            "id": self.collection.id,
            "slug": "test-slug2",
            "title": "TextCollection",
            "description": "Collection Description",
            "s3_storage": True,
            "start_date": None,
            "end_date": None,
            "status": Status.EDIT,
            "assets": [],
            "subcollections": [],
        }

        responses.add(
            responses.GET,
            "http://testserver/ws/collection/test-slug2/",
            json=collection_json,
            status=200,
        )

        # Act
        response = self.client.get("/transcribe/test-slug2/", {"page": 2})

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="transcriptions/project.html")

    def test_ExportCollectionView_get(self):
        """
        Test GET route /transcribe/export/<slug-value>/ (collection)
        :return:
        """

        # Arrange

        self.collection = Collection(
            title="TextCollection",
            slug="slug2",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        self.asset = Asset(
            title="TestAsset",
            slug="test-slug2",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            collection=self.collection,
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
            "b'Collection,Title,Description,MediaUrl,Transcription,Tags\\r\\n"
            "TextCollection,TestAsset,Asset Description,"
            "http://www.foo.com/1/2/3,,\\r\\n'",
        )

    @responses.activate
    def test_DeleteCollection_get(self):
        """
        Test GET route /transcribe/delete/<slug-value>/ (collection)
        :return:
        """

        # Arrange

        # add an item to Collection
        self.collection = Collection(
            title="TextCollection",
            slug="test-slug2",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        self.asset = Asset(
            title="TestAsset",
            slug="test-slug2",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            collection=self.collection,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset.save()

        # Mock REST api calls
        responses.add(responses.DELETE,
                      "http://testserver/ws/collection_delete/%s/" % (self.collection.slug, ),
                      status=200)



        # Act

        response = self.client.get("/transcribe/delete/test-slug2", follow=False)

        # Assert
        self.assertEqual(response.status_code, 301)

    @responses.activate
    def test_DeleteAsset_get(self):
        """
        Test GET route /transcribe/delete/asset/<slug-value>/ (asset)
        :return:
        """

        # Arrange

        # add an item to Collection
        self.collection = Collection(
            title="TextCollection",
            slug="test-collection-slug",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        self.asset = Asset(
            title="TestAsset",
            slug="test-asset-slug",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            collection=self.collection,
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
            collection=self.collection,
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.asset.save()

        # Mock REST calls
        collection_json = {
            "id": self.collection.id,
            "slug": self.collection.slug,
            "title": "TextCollection",
            "description": "Collection Description",
            "s3_storage": True,
            "start_date": None,
            "end_date": None,
            "status": Status.EDIT,
            "assets": [],
        }

        responses.add(
            responses.GET,
            "http://testserver/ws/collection/%s/" % (self.collection.slug, ),
            json=collection_json,
            status=200,
        )

        responses.add(responses.PUT,
                      "http://testserver/ws/asset_update/%s/%s/" % (self.collection.slug, self.asset.slug, ),
                      status=200)

        # Act

        response = self.client.get("/transcribe/%s/delete/asset/%s/" % (self.collection.slug, self.asset.slug, ),
                                   ollow=True)

        # Assert
        self.assertEqual(response.status_code, 302)

    @responses.activate
    def test_ConcordiaAssetView_post(self):
        """
        This unit test test the POST route /transcribe/<collection>/asset/<Asset_name>/
        :return:
        """
        # Arrange
        self.login_user()

        # create a collection
        self.collection = Collection(
            title="TestCollection",
            slug="Collection1",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        # create an Asset
        asset_slug = "Asset1"

        self.asset = Asset(
            title="TestAsset",
            slug=asset_slug,
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            collection=self.collection,
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
            "collection": {"slug": "Collection1"},
            "subcollection": None,
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
                "collection": {
                    "slug": "",
                    "title": "",
                    "description": "",
                    "s3_storage": False,
                    "start_date": None,
                    "end_date": None,
                    "status": None,
                    "assets": [],
                },
                "subcollection": None,
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
            "http://testserver/ws/page_in_use_filter/tester//transcribe/Collection1/asset/Asset1//",
            json={"count": 0, "results": []},
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/asset_by_slug/Collection1/Asset1/",
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
            "/transcribe/Collection1/asset/Asset1/",
            {"tx": "First Test Transcription", "tags": tag_name, "action": "Save"},
        )

        # Assert
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/transcribe/Collection1/asset/Asset1/")

    @responses.activate
    def test_ConcordiaAssetView_post_contact_community_manager(self):
        """
        This unit test test the POST route /transcribe/<collection>/asset/<Asset_name>/
        for an anonymous user. Clicking the contact community manager button
        should redirect to the contact us page.
        :return:
        """
        # Arrange

        # create a collection
        self.collection = Collection(
            title="TestCollection",
            slug="Collection1",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        asset_slug = "Asset1"

        self.asset = Asset(
            title="TestAsset",
            slug=asset_slug,
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            collection=self.collection,
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
            "collection": {"slug": "Collection1"},
            "subcollection": None,
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
                "collection": {
                    "slug": "",
                    "title": "",
                    "description": "",
                    "s3_storage": False,
                    "start_date": None,
                    "end_date": None,
                    "status": None,
                    "assets": [],
                },
                "subcollection": None,
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
            "http://testserver/ws/page_in_use_filter/AnonymousUser//transcribe/Collection1/asset/Asset1//",
            json={"count": 0, "results": []},
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/asset_by_slug/Collection1/Asset1/",
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
                      "http://testserver/ws/page_in_use_update/%s//transcribe/Collection1/asset/Asset1//" %
                      (self.anon_user.id, ),
                      status=200)

        responses.add(
            responses.GET,
            "http:////testserver/ws/anonymous_user/",
            json=anonymous_json,
            status=200
        )


        # Act
        response = self.client.get("/transcribe/Collection1/asset/Asset1/")
        self.assertEqual(response.status_code, 200)

        hash_ = re.findall(r'value="([0-9a-f]+)"', str(response.content))[0]
        captcha_response = CaptchaStore.objects.get(hashkey=hash_).response

        response = self.client.post(
            "/transcribe/Collection1/asset/Asset1/",
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
        This unit test test the POST route /transcribe/<collection>/asset/<Asset_name>/
        for an anonymous user. This user should not be able to tag
        :return:
        """
        # Arrange

        # create a collection
        self.collection = Collection(
            title="TestCollection",
            slug="Collection1",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        # create an Asset
        asset_slug = "Asset1"
        self.asset = Asset(
            title="TestAsset",
            slug=asset_slug,
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            collection=self.collection,
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
            "collection": {"slug": "Collection1"},
            "subcollection": None,
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
                "collection": {
                    "slug": "",
                    "title": "",
                    "description": "",
                    "s3_storage": False,
                    "start_date": None,
                    "end_date": None,
                    "status": None,
                    "assets": [],
                },
                "subcollection": None,
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
            "http://testserver/ws/page_in_use_filter/AnonymousUser//transcribe/Collection1/asset/Asset1//",
            json={"count": 0, "results": []},
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/asset_by_slug/Collection1/Asset1/",
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
                      "http://testserver/ws/page_in_use_update/%s//transcribe/Collection1/asset/Asset1//" %
                      (self.anon_user.id, ),
                      status=200)

        responses.add(
            responses.GET,
            "http:////testserver/ws/anonymous_user/",
            json=anonymous_json,
            status=200
        )

        # Act
        response = self.client.get("/transcribe/Collection1/asset/Asset1/")
        self.assertEqual(response.status_code, 200)
        hash_ = re.findall(r'value="([0-9a-f]+)"', str(response.content))[0]
        captcha_response = CaptchaStore.objects.get(hashkey=hash_).response

        response = self.client.post(
            "/transcribe/Collection1/asset/Asset1/",
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
        self.assertEqual(response.url, "/transcribe/Collection1/asset/Asset1/")

    @responses.activate
    def test_ConcordiaAssetView_post_anonymous_invalid_captcha(self):
        """
        This unit test test the POST route /transcribe/<collection>/asset/<Asset_name>/
        for an anonymous user with missing captcha. This user should not be able to tag
        also
        :return:
        """
        # Arrange

        # create a collection
        self.collection = Collection(
            title="TestCollection",
            slug="Collection1",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        # create an Asset
        asset_slug = "Asset1"
        self.asset = Asset(
            title="TestAsset",
            slug=asset_slug,
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            collection=self.collection,
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
            "collection": {"slug": "Collection1"},
            "subcollection": None,
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
                "collection": {
                    "slug": "",
                    "title": "",
                    "description": "",
                    "s3_storage": False,
                    "start_date": None,
                    "end_date": None,
                    "status": None,
                    "assets": [],
                },
                "subcollection": None,
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
            "http://testserver/ws/page_in_use_filter/AnonymousUser//transcribe/Collection1/asset/Asset1//",
            json={"count": 0, "results": []},
            status=200,
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/asset_by_slug/Collection1/Asset1/",
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
                      "http://testserver/ws/page_in_use_update/%s//transcribe/Collection1/asset/Asset1//" %
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
            "/transcribe/Collection1/asset/Asset1/",
            {"tx": "First Test Transcription", "tags": tag_name, "action": "Save"},
        )

        # Assert
        self.assertEqual(response.status_code, 200)

    @responses.activate
    def test_ConcordiaAssetView_get(self):
        """
        This unit test test the GET route /transcribe/<collection>/asset/<Asset_name>/
        with already in use. Verify the updated_on time is updated on PageInUse
        :return:
        """
        asset_slug = "Asset1"

        # Arrange
        self.login_user()

        # create a collection
        self.collection = Collection(
            title="TestCollection",
            slug="Collection1",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        # create an Asset
        self.asset = Asset(
            title="TestAsset",
            slug=asset_slug,
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            collection=self.collection,
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
            "collection": {"slug": "Collection1"},
            "subcollection": None,
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
                "collection": {
                    "slug": "",
                    "title": "",
                    "description": "",
                    "s3_storage": False,
                    "start_date": None,
                    "end_date": None,
                    "status": None,
                    "assets": [],
                },
                "subcollection": None,
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
            "http://testserver/ws/page_in_use_update/%s//transcribe/Collection1/asset/Asset1//" % (self.user.id, ),
            status=200)

        responses.add(
            responses.GET,
            "http://testserver/ws/page_in_use_user/%s//transcribe/Collection1/asset/Asset1//" % (self.user.id, ),
            json={"user": self.user.id},
            status=200
        )

        responses.add(
            responses.GET,
            "http://testserver/ws/asset_by_slug/Collection1/Asset1/",
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

        url = "/transcribe/Collection1/asset/Asset1/"

        # Act
        response = self.client.get(url)

        # Assert
        self.assertEqual(response.status_code, 200)

    @responses.activate
    def test_redirect_when_same_page_in_use(self):
        """
        Test the GET route for /transcribe/<collection>/alternateasset/<Asset_name>/
        :return:
        """
        # Arrange
        self.login_user()

        # create a collection
        self.collection = Collection(
            title="TestCollection",
            slug="Collection1",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        # create 2 Assets
        self.asset = Asset(
            title="TestAsset",
            slug="Asset1",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            collection=self.collection,
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
            collection=self.collection,
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
                "collection": {
                    "slug": "",
                    "title": "",
                    "description": "",
                    "s3_storage": False,
                    "start_date": None,
                    "end_date": None,
                    "status": None,
                    "assets": [],
                },
                "subcollection": None,
                "sequence": None,
                "metadata": None,
                "status": Status.EDIT,
            }

        responses.add(
            responses.GET,
            "http://testserver/ws/collection_asset_random/%s/%s" % (self.collection.slug, self.asset.slug,),
            json=asset_json,
            status=200,
        )

        # Act
        response = self.client.post(
            "/transcribe/alternateasset/",
            {"collection": self.collection.slug, "asset": self.asset.slug},
        )

        # Assert
        self.assertEqual(response.status_code, 200)

    @responses.activate
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
            "/transcribe/pageinuse/", {"page_url": url, "user": self.user}
        )

        # Assert
        self.assertEqual(response.status_code, 200)

    @responses.activate
    def test_ConcordiaProjectView_get(self):
        """
        Test GET on route /transcribe/<slug-value> (collection)
        :return:
        """

        # Arrange

        # add an item to Collection
        self.collection = Collection(
            title="TextCollection",
            slug="test-slug2",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        self.subcollection = Subcollection(
            title="TextCollection sub collection",
            slug="test-slug2-proj",
            metadata={"key": "val1"},
            status=Status.EDIT,
            collection=self.collection,
        )
        self.subcollection.save()

        self.subcollection1 = Subcollection(
            title="TextCollection sub collection1",
            slug="test-slug2-proj1",
            metadata={"key": "val1"},
            status=Status.EDIT,
            collection=self.collection,
        )
        self.subcollection1.save()

        # mock REST requests

        collection_json = {
            "id": self.collection.id,
            "slug": "test-slug2",
            "title": "TextCollection",
            "description": "Collection Description",
            "s3_storage": True,
            "start_date": None,
            "end_date": None,
            "status": Status.EDIT,
            "assets": [],
        }

        responses.add(
            responses.GET,
            "http://testserver/ws/collection/test-slug2/",
            json=collection_json,
            status=200,
        )

        # Act
        response = self.client.get("/transcribe/test-slug2/test-slug2-proj1/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/collection.html"
        )

    @responses.activate
    def test_ConcordiaProjectView_get_page2(self):
        """
        Test GET on route /transcribe/<slug-value>/ (collection) on page 2
        :return:
        """

        # Arrange

        # add an item to Collection
        self.collection = Collection(
            title="TextCollection",
            slug="test-slug2",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        self.subcollection = Subcollection(
            title="TextCollection sub collection",
            slug="test-slug2-proj",
            metadata={"key": "val1"},
            status=Status.EDIT,
            collection=self.collection,
        )
        self.subcollection.save()

        self.subcollection1 = Subcollection(
            title="TextCollection sub collection1",
            slug="test-slug2-proj1",
            metadata={"key": "val1"},
            status=Status.EDIT,
            collection=self.collection,
        )
        self.subcollection1.save()

        # mock REST requests

        collection_json = {
            "id": self.collection.id,
            "slug": "test-slug2",
            "title": "TextCollection",
            "description": "Collection Description",
            "s3_storage": True,
            "start_date": None,
            "end_date": None,
            "status": Status.EDIT,
            "assets": [],
        }

        responses.add(
            responses.GET,
            "http://testserver/ws/collection/test-slug2/",
            json=collection_json,
            status=200,
        )

        # Act
        response = self.client.get(
            "/transcribe/test-slug2/test-slug2-proj1/", {"page": 2}
        )

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/collection.html"
        )

    def test_FilterCollections_get(self):
        """Test list of filer collection get API"""

        # Arrange
        self.collection = Collection(
            title="TextCollection",
            slug="slug1",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        self.collection = Collection(
            title="Text Collection",
            slug="slug2",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        # Act
        response = self.client.get("/filter/collections/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)
        self.assertEqual(response.json()[0], "slug1")
        self.assertEqual(response.json()[1], "slug2")

    def test_FilterCollectionsWithParams_get(self):
        """Test list of filer collection get API"""

        # Arrange
        self.collection = Collection(
            title="TextCollection",
            slug="slug1",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        self.collection = Collection(
            title="Text Collection",
            slug="slug2",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        # Act
        response = self.client.get("/filter/collections/?name=sl")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)
        self.assertEqual(response.json()[0], "slug1")
        self.assertEqual(response.json()[1], "slug2")

    def test_FilterCollectionsEmpty_get(self):
        """Test list of filer collection get API"""

        # Arrange, to test empty filter collections. No need of arranging data

        # Act
        response = self.client.get("/filter/collections/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 0)

    def test_PublishCollectionView(self):
        """Test for updating status of a collection"""

        # Arrange
        self.collection = Collection(
            title="TextCollection",
            slug="slug1",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        self.subcollection = Subcollection(
            title="TextCollection sub collection",
            slug="test-slug2-proj",
            metadata={"key": "val1"},
            status=Status.EDIT,
            collection=self.collection,
        )
        self.subcollection.save()

        self.subcollection1 = Subcollection(
            title="TextCollection sub collection1",
            slug="test-slug2-proj1",
            metadata={"key": "val1"},
            status=Status.EDIT,
            collection=self.collection,
        )
        self.subcollection1.save()

        # Act
        response = self.client.get("/transcribe/publish/collection/slug1/true/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], True)

    def test_UnpublishCollectionView(self):
        """Test for updating status of a collection"""

        # Arrange
        self.collection = Collection(
            title="TextCollection",
            slug="slug1",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
            is_publish=True,
        )
        self.collection.save()

        self.subcollection = Subcollection(
            title="TextCollection sub collection",
            slug="test-slug2-proj",
            metadata={"key": "val1"},
            status=Status.EDIT,
            collection=self.collection,
            is_publish=True,
        )
        self.subcollection.save()

        self.subcollection1 = Subcollection(
            title="TextCollection sub collection1",
            slug="test-slug2-proj1",
            metadata={"key": "val1"},
            status=Status.EDIT,
            collection=self.collection,
            is_publish=True,
        )
        self.subcollection1.save()

        # Act
        response = self.client.get("/transcribe/publish/collection/slug1/false/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], False)

    def test_PublishProjectView(self):
        """Test for updating status of a project"""

        # Arrange
        self.collection = Collection(
            title="TextCollection",
            slug="slug1",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        self.subcollection = Subcollection(
            title="TextCollection sub collection",
            slug="test-slug2-proj",
            metadata={"key": "val1"},
            status=Status.EDIT,
            collection=self.collection,
        )
        self.subcollection.save()

        self.subcollection1 = Subcollection(
            title="TextCollection sub collection1",
            slug="test-slug2-proj1",
            metadata={"key": "val1"},
            status=Status.EDIT,
            collection=self.collection,
        )
        self.subcollection1.save()

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
        self.collection = Collection(
            title="TextCollection",
            slug="slug1",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
            is_publish=True,
        )
        self.collection.save()

        self.subcollection = Subcollection(
            title="TextCollection sub collection",
            slug="test-slug2-proj",
            metadata={"key": "val1"},
            status=Status.EDIT,
            collection=self.collection,
            is_publish=True,
        )
        self.subcollection.save()

        self.subcollection1 = Subcollection(
            title="TextCollection sub collection1",
            slug="test-slug2-proj1",
            metadata={"key": "val1"},
            status=Status.EDIT,
            collection=self.collection,
            is_publish=True,
        )
        self.subcollection1.save()

        # Act
        response = self.client.get(
            "/transcribe/publish/project/slug1/test-slug2-proj/false/"
        )

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], False)
