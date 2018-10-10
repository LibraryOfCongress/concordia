# TODO: Add correct copyright header

import json

from django.test import TestCase
from django.urls import reverse
from rest_framework import status

from concordia.models import (
    MediaType,
    Status,
    Tag,
    Transcription,
    User,
    UserAssetTagCollection,
)

from .utils import create_asset


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
        self.user = User.objects.create(username="tester", email="tester@example.com")
        self.user.set_password("top_secret")
        self.user.save()

        self.client.login(username="tester", password="top_secret")

        # create a session cookie
        self.client.session["foo"] = 123  # HACK: needed for django Client

    def test_Transcriptions_latest_get(self):
        """
        Test getting latest transcription for an asset. route ws/transcriptions/asset/
        """

        self.login_user()

        # create a second user
        username = "tester2"
        self.user2 = User.objects.create(username=username, email="tester2@example.com")
        self.user2.set_password("top_secret")
        self.user2.save()

        asset1 = create_asset(
            title="Test Asset 1",
            media_url="http://www.example.com/1/2/3",
            media_type=MediaType.IMAGE,
            status=Status.EDIT,
        )

        # add Transcription objects
        transcription1 = Transcription(
            asset=asset1, user_id=self.user.id, status=Status.EDIT, text="T1"
        )
        transcription1.full_clean()
        transcription1.save()

        transcription2 = Transcription(
            asset=asset1, user_id=self.user2.id, status=Status.EDIT, text="T2"
        )
        transcription2.full_clean()
        transcription2.save()

        response = self.client.get("/ws/transcription/%s/" % asset1.id)

        json_resp = json.loads(response.content)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(json_resp["text"], transcription2.text)

    def test_Transcriptions_create_post(self):
        """
        Test creating a transcription. route ws/transcription_create/
        """

        self.login_user()

        asset = create_asset(
            title="TestAsset",
            media_url="http://www.example.com/1/2/3",
            media_type=MediaType.IMAGE,
            status=Status.EDIT,
        )

        response = self.client.post(
            reverse("ws:submit-transcription", kwargs={"asset_pk": asset.pk}),
            {"user_id": self.user.id, "status": Status.EDIT, "text": "T1"},
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Get all Transcriptions for the asset
        transcriptions_count = Transcription.objects.filter(asset=asset).count()
        self.assertEqual(transcriptions_count, 1)

        # Add Another transcription
        response = self.client.post(
            reverse("ws:submit-transcription", kwargs={"asset_pk": asset.pk}),
            {"user_id": self.user.id, "status": Status.EDIT, "text": "T2"},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Get all Transcriptions for the asset, should be another one
        transcriptions_count = Transcription.objects.filter(asset=asset).count()
        self.assertEqual(transcriptions_count, 2)

    def test_GetTags_get(self):
        """
        Test getting the tags for an asset, route /ws/tags/<asset>
        """

        self.login_user()

        # create a second user
        username = "tester2"
        user2 = User.objects.create(username=username, email="tester2@example.com")
        user2.set_password("top_secret")
        user2.save()

        asset = create_asset(
            title="TestAsset",
            media_url="http://www.example.com/1/2/3",
            media_type=MediaType.IMAGE,
            status=Status.EDIT,
        )

        tag1 = Tag.objects.create(value="Tag1")
        tag2 = Tag.objects.create(value="Tag2")
        tag3 = Tag.objects.create(value="Tag3")

        # Save for User1
        asset_tag_collection = UserAssetTagCollection(asset=asset, user_id=self.user.id)
        asset_tag_collection.save()
        asset_tag_collection.tags.add(tag1, tag2)

        # Save for User2
        asset_tag_collection2 = UserAssetTagCollection(asset=asset, user_id=user2.id)
        asset_tag_collection2.save()
        asset_tag_collection2.tags.add(tag3)

        response = self.client.get(reverse("ws:get-tags", args=(asset.pk,)))

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
        user2 = User.objects.create(username=username, email="tester2@example.com")
        user2.set_password("top_secret")
        user2.save()

        asset = create_asset()

        response = self.client.get(
            reverse("ws:submit-tags", kwargs={"asset_pk": asset.id})
        )

        json_resp = json.loads(response.content)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(json_resp["results"]), 0)
