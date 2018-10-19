from django.test import TestCase
from django.urls import reverse
from rest_framework import status

from concordia.models import MediaType, Transcription, User

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

    def test_Transcriptions_create_post(self):
        """
        Test creating a transcription. route ws/transcription_create/
        """

        self.login_user()

        asset = create_asset(
            title="TestAsset",
            media_url="http://www.example.com/1/2/3",
            media_type=MediaType.IMAGE,
        )

        response = self.client.post(
            reverse("save-transcription", kwargs={"asset_pk": asset.pk}),
            {"user_id": self.user.id, "text": "T1"},
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Get all Transcriptions for the asset
        transcriptions_count = Transcription.objects.filter(asset=asset).count()
        self.assertEqual(transcriptions_count, 1)

        # Add Another transcription
        response = self.client.post(
            reverse("save-transcription", kwargs={"asset_pk": asset.pk}),
            {
                "user_id": self.user.id,
                "text": "T2",
                "supersedes": Transcription.objects.get().pk,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Get all Transcriptions for the asset, should be another one
        transcriptions_count = Transcription.objects.filter(asset=asset).count()
        self.assertEqual(transcriptions_count, 2)
