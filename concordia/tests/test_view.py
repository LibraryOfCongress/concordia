# TODO: Add correct copyright header

import os
import sys
import tempfile
from unittest.mock import Mock, patch

import views
from django.test import Client, TestCase
from PIL import Image

from concordia.models import (Asset, Collection, MediaType, Status,
                              Transcription, User, UserProfile)

PACKAGE_PARENT = ".."
SCRIPT_DIR = os.path.dirname(
    os.path.realpath(os.path.join(os.getcwd(), os.path.expanduser(__file__)))
)
sys.path.append(os.path.normpath(os.path.join(SCRIPT_DIR, PACKAGE_PARENT)))
sys.path.append(os.path.join(SCRIPT_DIR, "../"))
sys.path.append(os.path.join(SCRIPT_DIR, "../../config"))


from config import Config



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

        # make sure the config-optional-override.json mode is "unittest"
        self.assertEqual(Config.GetOverrideMode(), "unittest")

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

        login = self.client.login(username="tester", password="top_secret")

    def test_concordia_api(self):
        """
        Test the tracribr_api. Provide a mock of requests
        :return:
        """

        # Arrange

        relative_path = Mock()

        with patch("views.requests") as mock_requests:
            mock_requests.get.return_value = mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"concordia_data": "abc123456"}

            # Act
            results = views.concordia_api("relative_path")

            # Assert
            self.assertEqual(results["concordia_data"], "abc123456")

    def test_AccountProfileView_get(self):
        """
        Test the http GET on route account/profile
        :return:
        """

        # Arrange

        self.login_user()

        # create a collection
        self.collection = Collection(
            title="TextCollection",
            slug="www.foo.com/slug2",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.PCT_0,
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
            status=Status.PCT_0,
        )
        self.asset.save()

        # add a Transcription object
        self.transcription = Transcription(
            asset=self.asset, user_id=self.user.id, status=Status.PCT_0
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

        # Arrange
        self.login_user()

        # Act
        response = self.client.post(
            "/account/profile/",
            {
                "first_name": "Jimmy",
                "email": "tester@foo.com",
                "username": "tester",
                "password1": "",
                "password2": "",
            },
        )

        # Assert
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/account/profile/")

        # Verify the User was correctly updated
        updated_user = User.objects.get(id=self.user.id)
        self.assertEqual(updated_user.first_name, "Jimmy")

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
        self.assertEqual(response.url, "/account/profile/")

        # Verify the User was not changed
        updated_user = User.objects.get(id=self.user.id)
        self.assertEqual(updated_user.first_name, "")

    def test_AccountProfileView_post_new_password(self):
        """
        This unit test test the post entry for the route account/profile with new password
        :param self:
        :return:
        """

        # Arrange
        self.login_user()

        # Act
        response = self.client.post(
            "/account/profile/",
            {
                "first_name": "Jimmy",
                "email": "tester@foo.com",
                "username": "tester",
                "password1": "abc",
                "password2": "abc",
            },
        )

        # Assert
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/account/profile/")

        # Verify the User was correctly updated
        updated_user = User.objects.get(id=self.user.id)
        self.assertEqual(updated_user.first_name, "Jimmy")

        # logout and login with new password
        logout = self.client.logout()
        login2 = self.client.login(username="tester", password="abc")

        self.assertTrue(login2)

    def test_AccountProfileView_post_with_image(self):
        """
        This unit test tests the post entry for the route account/profile with new image file
        :param self:
        :return:
        """

        # Arrange
        self.login_user()

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
                    "first_name": "Jimmy",
                    "email": "tester@foo.com",
                    "username": "tester",
                    "password1": "",
                    "password2": "",
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
            status=Status.PCT_0,
        )
        self.collection.save()

        # Act
        response = self.client.get("/transcribe/test-slug2/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/collection.html"
        )

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
            status=Status.PCT_0,
        )
        self.collection.save()

        # Act
        response = self.client.get("/transcribe/test-slug2/", {"page": 2})

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/collection.html"
        )

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
            status=Status.PCT_0,
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
            status=Status.PCT_0,
        )
        self.asset.save()

        # Act
        response = self.client.get("/transcribe/export/slug2/")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            str(response.content),
            "b'Collection,Title,Description,MediaUrl,Transcription,Tags\\r\\nTextCollection,TestAsset,Asset Description,http://www.foo.com/1/2/3,,\\r\\n'",
        )

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
            status=Status.PCT_0,
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
            status=Status.PCT_0,
        )
        self.asset.save()

        # Act
        response = self.client.get("/transcribe/delete/test-slug2", follow=True)

        # Assert
        self.assertEqual(response.status_code, 200)

        # verify the collection is not in db
        collection2 = Collection.objects.all()
        self.assertEqual(len(collection2), 0)
