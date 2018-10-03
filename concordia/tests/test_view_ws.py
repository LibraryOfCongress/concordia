# TODO: Add correct copyright header

import json
import logging
import time
from datetime import datetime, timedelta

from django.test import TestCase
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
    UserAssetTagCollection,
    UserProfile,
)


class WebServiceViewTests(TestCase):
    """
    This class contains the unit tests for the view_ws in the concordia app.

    Make sure the postgresql db is available. Run docker-compose up db
    """

    def login_user(self):
        """
        Create a user and log the user in
        """

        # create user and login
        self.user = User.objects.create(username="tester", email="tester@foo.com")
        self.user.set_password("top_secret")
        self.user.save()

        login_result = self.client.login(username="tester", password="top_secret")

        # create a session cookie
        self.client.session["foo"] = 123  # HACK: needed for django Client

    def test_AnonymousUser_get(self):
        """
        This unit test tests the get  route ws/anonymous_user/
        :param self:
        """

        self.login_user()

        response = self.client.get("/ws/anonymous_user/")
        response2 = self.client.get("/ws/anonymous_user/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.content, response2.content)

    def test_PageInUse_post(self):
        """
        This unit test tests the post entry for the route ws/page_in_use
        :param self:
        """

        self.login_user()

        response = self.client.post(
            "/ws/page_in_use/",
            {
                "page_url": "campaigns/American-Jerusalem/asset/mamcol.0930/",
                "user": self.user.id,
                "updated_on": datetime.now(),
            },
        )

        self.assert_post_successful(response)

    def test_PageInUse_delete_old_entries_post(self):
        """
        This unit test tests the post entry for the route ws/page_in_use
        the database has two items added the created_on timestamp of now - 10 minutes
        :param self:
        """

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

        response = self.client.post(
            "/ws/page_in_use/",
            {
                "page_url": "campaigns/American-Jerusalem/asset/mamcol.0930/",
                "user": self.user.id,
                "updated_on": datetime.now(),
            },
        )

        self.assert_post_successful(response)

    def test_PageInUse_nologin_post(self):
        """
        This unit test tests the post entry for the route ws/page_in_use without logging in
        :param self:
        """

        # create user
        self.user = User.objects.create(username="foo", email="tester@foo.com")
        self.user.set_password("top_secret")
        self.user.save()

        response = self.client.post(
            "/ws/page_in_use/",
            {
                "page_url": "campaigns/American-Jerusalem/asset/mamcol.0930/",
                "user": self.user.id,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # Verify the entry is not in the PagInUse table
        page_in_use = PageInUse.objects.all()
        self.assertEqual(len(page_in_use), 0)

    def test_PageInUse_nologin_anonymous_post(self):
        """
        This unit test tests the post entry for the route ws/page_in_use without logging
        and the user is anonymous
        :param self:
        """

        # create user
        self.user = User.objects.create(username="anonymous", email="tester@foo.com")
        self.user.set_password("top_secret")
        self.user.save()

        response = self.client.post(
            "/ws/page_in_use/",
            {
                "page_url": "campaigns/American-Jerusalem/asset/mamcol.0930/",
                "user": self.user.id,
                "updated_on": datetime.now(),
            },
        )

        self.assert_post_successful(response)

    def assert_post_successful(self, response):
        """
        Check the results of a successful post and insert of a PageInUse database item
        :param response:
        """

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify the entry is in the PagInUse table
        page_in_use = PageInUse.objects.all()
        self.assertEqual(len(page_in_use), 1)

    def test_PageInUse_get(self):
        """
        This unit test tests the get entry for the route ws/page_in_use/url
        :param self:
        """

        self.login_user()

        # Add two values to database
        PageInUse.objects.create(page_url="foo.com/blah", user=self.user)

        page_in_use = PageInUse.objects.create(page_url="bar.com/blah", user=self.user)

        response = self.client.get("/ws/page_in_use/bar.com/blah/")

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
        """

        self.login_user()

        # create second user
        self.user2 = User.objects.create(username="bar", email="tester2@foo.com")
        self.user2.set_password("top_secret")
        self.user2.save()

        test_page_url = "foo.com/blah"
        # Add two values to database
        page_in_use = PageInUse.objects.create(page_url=test_page_url, user=self.user)

        PageInUse.objects.create(page_url="bar.com/blah", user=self.user2)

        response = self.client.get(
            "/ws/page_in_use_user/%s/%s/" % (self.user.id, test_page_url)
        )

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
        """

        self.login_user()

        # Add a value to database
        page = PageInUse(page_url="foo.com/blah", user=self.user)
        page.save()

        min_update_time = page.created_on + timedelta(seconds=2)

        # sleep so update time can be tested against original time
        time.sleep(2)

        change_page_in_use = {"page_url": "foo.com/blah", "user": self.user.id}

        response = self.client.put(
            "/ws/page_in_use_update/foo.com/blah/",
            data=json.dumps(change_page_in_use),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        updated_page = PageInUse.objects.filter(page_url="foo.com/blah")
        self.assertTrue(len(updated_page), 1)
        self.assertEqual(page.id, updated_page[0].id)
        self.assertTrue(updated_page[0].updated_on > min_update_time)

    def test_PageInUse_delete(self):
        """
        This unit test tests the delete of an existing PageInUse using DELETE on route ws/page_in_use_delete/
        """

        self.login_user()

        # Add a value to database
        page = PageInUse(page_url="foo.com/blah", user=self.user)
        page.save()

        current_page_in_use_count = PageInUse.objects.all().count()

        response = self.client.delete("/ws/page_in_use_delete/%s/" % "foo.com/blah")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        deleted_page_in_use_count = PageInUse.objects.all().count()

        deleted_page = PageInUse.objects.filter(page_url="foo.com/blah")
        self.assertEqual(len(deleted_page), 0)
        self.assertEqual(current_page_in_use_count - 1, deleted_page_in_use_count)

    def test_PageInUse_filter_get(self):
        """
        Test the route ws/page_in_use_filter/user/page_url/
        It should return a list of PageInUse updated in last 5 minutes by user other than self.user
        """

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

        response = self.client.get(
            "/ws/page_in_use_filter/%s/%s/" % (self.user.username, test_url)
        )

        json_resp = json.loads(response.content)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(json_resp["results"]) > 0)

    def test_PageInUse_filter_no_pages_get(self):
        """
        Test the route ws/page_in_use_filter/user/page_url/
        It should return an empty list
        """

        self.login_user()

        # create a second user
        username = "tester2"
        test_url = "bar.com/blah"
        self.user2 = User.objects.create(username=username, email="tester2@foo.com")
        self.user2.set_password("top_secret")
        self.user2.save()

        response = self.client.get(
            "/ws/page_in_use_filter/%s/%s/" % (self.user.username, test_url)
        )

        json_resp = json.loads(response.content)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(json_resp["results"]), 0)

    def test_Transcriptions_latest_get(self):
        """
        Test getting latest transcription for an asset. route ws/transcriptions/asset/
        """

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

        response = self.client.get("/ws/transcription/%s/" % self.asset.id)

        json_resp = json.loads(response.content)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(json_resp["text"], t2_text)

    def test_Transcriptions_by_user(self):
        """
        Test getting the user's transcriptions. route ws/transcription_by_user/<userid>/
        """

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

        response = self.client.get("/ws/transcription_by_user/%s/" % self.user.id)

        json_resp = json.loads(response.content)
        transcriptions_array = []
        for trans in json_resp["results"]:
            transcriptions_array.append(trans["text"])

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(json_resp["count"], 2)
        self.assertTrue("T3" in transcriptions_array)
        self.assertTrue("T1" in transcriptions_array)
        self.assertFalse("T2" in transcriptions_array)

    def test_Transcriptions_create_post(self):
        """
        Test creating a transcription. route ws/transcription_create/
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

        response = self.client.post(
            "/ws/transcription_create/",
            {
                "asset": self.asset.id,
                "user_id": self.user.id,
                "status": Status.EDIT,
                "text": "T1",
            },
        )

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

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_GetTags_get(self):
        """
        Test getting the tags for an asset, route /ws/tags/<asset>
        """

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

        response = self.client.get("/ws/tags/%s/" % self.asset.id)

        json_resp = json.loads(response.content)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(json_resp["results"]), 3)

    def test_GetTags_notags_get(self):
        """
        Test getting the tags for an asset when no tags exist, route /ws/tags/<asset>
        """

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

        response = self.client.get("/ws/tags/%s/" % self.asset.id)

        json_resp = json.loads(response.content)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(json_resp["results"]), 0)
