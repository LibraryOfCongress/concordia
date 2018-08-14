# TODO: Add correct copyright header

from datetime import datetime, timedelta
import json
import time
from django.test import Client, TestCase
from django.utils.encoding import force_text
import logging
from rest_framework import status

from concordia.models import PageInUse, User, Collection, Status, Asset, MediaType, \
    Transcription, Tag, UserAssetTagCollection

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
        self.client.session['foo'] = 123  # HACK: needed for django Client

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
                "page_url": "transcribe/American-Jerusalem/asset/mamcol.0930/",
                "user": self.user.id,
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
            updated_on=time_threshold)
        page1.save()

        page2 = PageInUse(
            page_url="bar.com/blah",
            user=self.user,
            created_on=time_threshold,
            updated_on=time_threshold)
        page2.save()

        pages_in_use = PageInUse.objects.all()
        for p in pages_in_use:
            print(p.page_url, p.created_on, p.updated_on)

        # Act
        response = self.client.post(
            "/ws/page_in_use/",
            {
                "page_url": "transcribe/American-Jerusalem/asset/mamcol.0930/",
                "user": self.user.id,
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
                "page_url": "transcribe/American-Jerusalem/asset/mamcol.0930/",
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
                "page_url": "transcribe/American-Jerusalem/asset/mamcol.0930/",
                "user": self.user.id,
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
        PageInUse.objects.create(
            page_url="foo.com/blah",
            user=self.user)

        PageInUse.objects.create(
            page_url="bar.com/blah",
            user=self.user)

        # Act
        response = self.client.get("/ws/page_in_use/bar.com/blah/")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertJSONEqual(
            str(response.content, encoding='utf8'),
            {"page_url": "bar.com/blah", "user": self.user.id }
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
        PageInUse.objects.create(
            page_url=test_page_url,
            user=self.user)

        PageInUse.objects.create(
            page_url="bar.com/blah",
            user=self.user2)

        # Act
        response = self.client.get("/ws/page_in_use_user/%s/%s/" % (self.user.id, test_page_url))

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertJSONEqual(
            str(response.content, encoding='utf8'),
            {"page_url": test_page_url, "user": self.user.id }
        )

    def test_PageInUse_put(self):
        """
        This unit test tests the update of an existing PageInUse using PUT on route ws/page_in_use/url
        :return:
        """
        # Arrange
        self.login_user()

        # Add a value to database
        page = PageInUse(
            page_url="foo.com/blah",
            user=self.user)
        page.save()

        min_update_time = page.created_on + timedelta(seconds=2)

        change_page_in_use = {"page_url": "foo.com/blah", "user": self.user.id}

        # sleep so update time can be tested against original time
        time.sleep(2)

        # Act
        response = self.client.put(
            "/ws/page_in_use_update/foo.com/blah/",
            data=json.dumps(change_page_in_use),
            content_type='application/json'
        )

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        updated_page = PageInUse.objects.filter(page_url="foo.com/blah")
        self.assertTrue(len(updated_page), 1)
        self.assertEqual(page.id, updated_page[0].id)
        self.assertTrue(updated_page[0].updated_on > min_update_time)

    def test_Collection_get(self):
        """
        Test getting a Collection object
        :return:
        """
        # Arrange
        self.login_user()

        # create 2 collections
        self.collection = Collection(
            title="TextCollection",
            slug="slug1",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        self.collection2 = Collection(
            title="TextCollection2",
            slug="slug2",
            description="Collection2 Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection2.save()

        # Act
        response = self.client.get("/ws/collection/slug2/")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertJSONEqual(
            str(response.content, encoding='utf8'),
            {'description': 'Collection2 Description',
             'end_date': None,
             'id': self.collection2.id,
             'slug': 'slug2',
             'start_date': None,
             'status': Status.EDIT,
             'title': 'TextCollection2'}
        )

    def test_get_assets_by_collection(self):
        """
        Test getting a list of assets by collection
        :return:
        """

        # Arrange
        self.login_user()

        # create 2 collections
        self.collection = Collection(
            title="TextCollection",
            slug="slug1",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        self.collection2 = Collection(
            title="TextCollection2",
            slug="slug2",
            description="Collection2 Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection2.save()

        # Add 2 assets to collection2, 1 asset to collection1
        self.asset = Asset(
            title="TestAsset",
            slug="Asset1",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            collection=self.collection2,
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
            collection=self.collection2,
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
            collection=self.collection,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset3.save()

        # Act
        response = self.client.get("/ws/asset/slug2/")

        json_resp = json.loads(response.content)

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(json_resp['results']), 2)

    def test_get_assets_by_collection_and_slug(self):
        """
        Test getting an asset by collection and slug
        :return:
        """

        # Arrange
        self.login_user()

        # create 2 collections
        self.collection = Collection(
            title="TextCollection",
            slug="slug1",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        self.collection2 = Collection(
            title="TextCollection2",
            slug="slug2",
            description="Collection2 Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection2.save()

        # Add 2 assets to collection2, 1 asset to collection1
        self.asset = Asset(
            title="TestAsset",
            slug="Asset1",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            collection=self.collection2,
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
            collection=self.collection2,
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
            collection=self.collection,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset3.save()

        # Act
        response = self.client.get("/ws/asset_by_slug/slug1/Asset3/")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertJSONEqual(
            force_text(response.content),
            {
                "title": "TestAsset3",
                "slug": "Asset3",
                "description": "Asset Description",
                "media_url": "http://www.foo.com/1/2/3",
                "media_type": MediaType.IMAGE,
                "collection": self.collection.id,
                "sequence": 1,
                "metadata": {"key": "val2"},
                "subcollection": None,
                "status": Status.EDIT,
            }
        )

    def test_get_assets_by_collection_and_slug_no_match(self):
        """
        Test getting an asset by collection and slug using a slug that doesn't exist
        :return:
        """

        # Arrange
        self.login_user()

        # create 2 collections
        self.collection = Collection(
            title="TextCollection",
            slug="slug1",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        self.collection2 = Collection(
            title="TextCollection2",
            slug="slug2",
            description="Collection2 Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection2.save()

        # Add 2 assets to collection2, 1 asset to collection1
        self.asset = Asset(
            title="TestAsset",
            slug="Asset1",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            collection=self.collection2,
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
            collection=self.collection2,
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
            collection=self.collection,
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
                "collection": None,
                "sequence": None,
                "metadata": None,
                "subcollection": None,
                "status": None,
            }
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
        PageInUse.objects.create(
            page_url="foo.com/blah",
            user=self.user)

        PageInUse.objects.create(
            page_url=test_url,
            user=self.user2)

        # Act
        response = self.client.get("/ws/page_in_use_filter/%s/%s/" % (self.user.username, test_url, ))

        json_resp = json.loads(response.content)

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(json_resp['results']) > 0)

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
        response = self.client.get("/ws/page_in_use_filter/%s/%s/" % (self.user.username, test_url, ))

        json_resp = json.loads(response.content)

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(json_resp['results']), 0)

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

        # create a collection
        self.collection = Collection(
            title="TextCollection",
            slug="www.foo.com/slug2",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        # create Assets
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

        self.asset2 = Asset(
            title="TestAsset2",
            slug="www.foo.com/slug2",
            description="Asset Description",
            media_url="http://www.foo.com/1/2/3",
            media_type=MediaType.IMAGE,
            collection=self.collection,
            metadata={"key": "val2"},
            status=Status.EDIT,
        )
        self.asset2.save()

        # add Transcription objects
        self.transcription = Transcription(
            asset=self.asset,
            user_id=self.user.id,
            status=Status.EDIT,
            text="T1"
        )
        self.transcription.save()

        t2_text = "T2"

        self.transcription2 = Transcription(
            asset=self.asset,
            user_id=self.user2.id,
            status=Status.EDIT,
            text=t2_text
        )
        self.transcription2.save()

        # Act

        response = self.client.get("/ws/transcription/%s/" % self.asset.id)

        json_resp = json.loads(response.content)

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(json_resp["text"], t2_text)

    def test_Transcriptions_create_post(self):
        """
        Test creating a transcription. route ws/transcription_create/
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
            status=Status.EDIT,
        )
        self.collection.save()

        # create Assets
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

        # Act
        response = self.client.post(
            "/ws/transcription_create/",
            {
                "asset": self.asset.id,
                "user_id": self.user.id,
                "status": Status.EDIT,
                "text": "T1"

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
                "text": "T2"

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

        # create a collection
        self.collection = Collection(
            title="TextCollection",
            slug="www.foo.com/slug2",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        # create Assets
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

        # Act
        response = self.client.post(
            "/ws/tag_create/",
            {
                "collection": self.collection.slug,
                "asset": self.asset.slug,
                "user_id": self.user.id,
                "name": "T1",
                "value": "T1"
            },
        )

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_Tag_create_with_an_existing_tag_post(self):
        """
        Test creating a tag, adding to an asset that already has a tag. route ws/tag_create/
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
            status=Status.EDIT,
        )
        self.collection.save()

        # create Assets
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

        # Act
        response = self.client.post(
            "/ws/tag_create/",
            {
                "collection": self.collection.slug,
                "asset": self.asset.slug,
                "user_id": self.user.id,
                "name": "T1",
                "value": "T1"
            },
        )

        response = self.client.post(
            "/ws/tag_create/",
            {
                "collection": self.collection.slug,
                "asset": self.asset.slug,
                "user_id": self.user.id,
                "name": "T2",
                "value": "T3"
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

        # create a collection
        self.collection = Collection(
            title="TextCollection",
            slug="www.foo.com/slug2",
            description="Collection Description",
            metadata={"key": "val1"},
            status=Status.EDIT,
        )
        self.collection.save()

        # create Assets
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

        self.tag1 = Tag(
            name="Tag1",
            value="Tag1"
        )
        self.tag1.save()

        self.tag2 = Tag(
            name="Tag2",
            value="Tag2"
        )
        self.tag2.save()

        self.tag3 = Tag(
            name="Tag3",
            value="Tag3"
        )
        self.tag3.save()

        # Save for User1
        self.asset_tag_collection = UserAssetTagCollection(
            asset=self.asset,
            user_id=self.user.id
        )
        self.asset_tag_collection.save()
        self.asset_tag_collection.tags.add(self.tag1, self.tag2)

        # Save for User2
        self.asset_tag_collection2 = UserAssetTagCollection(
            asset=self.asset,
            user_id=self.user2.id
        )
        self.asset_tag_collection2.save()
        self.asset_tag_collection2.tags.add(self.tag3)

        # Act
        response = self.client.get("/ws/tags/%s/" % self.asset.id)

        json_resp = json.loads(response.content)

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(json_resp["results"]), 3)


