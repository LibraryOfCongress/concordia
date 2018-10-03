# TODO: Add correct copyright header

import re

from captcha.models import CaptchaStore
from django.test import TestCase

from concordia.models import PageInUse, Status, User
from concordia.views import get_anonymous_user
from .utils import create_campaign, create_project, create_item, create_asset


class ViewTest_Concordia(TestCase):
    """
    This class contains the unit tests for the view in the concordia app.

    Make sure the postgresql db is available. Run docker-compose up db
    """

    def login_user(self):
        """
        Create a user and log the user in
        """

        # create user and login
        self.user = User.objects.create_user(username="tester", email="tester@example.com")
        self.user.set_password("top_secret")
        self.user.save()

        self.client.login(username="tester", password="top_secret")

    def test_AccountProfileView_get(self):
        """
        Test the http GET on route account/profile
        """

        self.login_user()

        response = self.client.get("/account/profile/")

        # validate the web page has the "tester" and "tester@example.com" as values
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="account/profile.html")

    def test_AccountProfileView_post(self):
        """
        This unit test tests the post entry for the route account/profile
        :param self:
        """
        test_email = "tester@example.com"

        self.login_user()

        response = self.client.post(
            "/account/profile/", {"email": test_email, "username": "tester"}
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/account/profile/")

        # Verify the User was correctly updated
        updated_user = User.objects.get(email=test_email)
        self.assertEqual(updated_user.email, test_email)

    def test_AccountProfileView_post_invalid_form(self):
        """
        This unit test tests the post entry for the route account/profile but
        submits an invalid form
        """
        self.login_user()

        response = self.client.post("/account/profile/", {"first_name": "Jimmy"})

        self.assertEqual(response.status_code, 200)

        # Verify the User was not changed
        updated_user = User.objects.get(id=self.user.id)
        self.assertEqual(updated_user.first_name, "")

    def test_campaign_list_view(self):
        """
        Test the GET method for route /campaigns
        """
        response = self.client.get("/campaigns/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/campaign_list.html"
        )

        # TODO: insert campaign and test its presence

    def test_campaign_detail_view(self):
        """
        Test GET on route /campaigns/<slug-value> (campaign)
        """
        c = create_campaign(title="GET Campaign", slug="get-campaign")

        response = self.client.get("/campaigns/get-campaign/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/campaign_detail.html"
        )
        self.assertIn(c.title, response.content)

    def test_concordiaCampaignView_get_page2(self):
        """
        Test GET on route /campaigns/<slug-value>/ (campaign) on page 2
        """
        c = create_campaign()

        response = self.client.get("/campaigns/%s/" % c.slug, {"page": 2})

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, template_name="transcriptions/campaign_detail.html"
        )

    def test_ConcordiaItemView_get(self):
        """
        Test GET on route /campaigns/<campaign-slug>/<project-slug>/<item-slug>
        """
        i = create_item()

        response = self.client.get(
            "/campaigns/%s/%s/%s/" % (i.project.campaign.slug, i.project.slug, i.slug)
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="transcriptions/item.html")
        self.assertIn(i.title, response.content)

    def test_ExportCampaignView_get(self):
        """
        Test GET route /campaigns/export/<slug-value>/ (campaign)
        """
        asset = create_asset()

        response = self.client.get("/campaigns/exportCSV/%s/" % asset.campaign.slug)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            str(response.content),
            "b'Campaign,Title,Description,MediaUrl,Transcription,Tags\\r\\n"
            "TextCampaign,TestAsset,Asset Description,"
            "http://www.example.com/1/2/3,,\\r\\n'",
        )

    def test_ConcordiaAssetView_post_anonymous_happy_path(self):
        """
        This unit test test the POST route /campaigns/<campaign>/asset/<Asset_name>/
        for an anonymous user. This user should not be able to tag
        """
        asset = create_asset()
        anonymous_user = get_anonymous_user()

        transcription = asset.transcription_set.create(
            user_id=anonymous_user.pk, text="Test transcription 1", status=Status.EDIT
        )
        transcription.full_clean()
        transcription.save()

        tag_name = "Test tag 1"

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

    def test_ConcordiaAssetView_post_anonymous_invalid_captcha(self):
        """
        This unit test test the POST route /campaigns/<campaign>/asset/<Asset_name>/
        for an anonymous user with missing captcha. This user should not be able to tag
        also
        """

        asset = create_asset()
        anonymous_user = get_anonymous_user()

        transcription = asset.transcription_set.create(
            user_id=anonymous_user.pk, text="Test transcription 1", status=Status.EDIT
        )
        transcription.full_clean()
        transcription.save()

        tag_name = "Test tag 1"

        # post as anonymous user without captcha data
        response = self.client.post(
            "/campaigns/Campaign1/asset/Asset1/",
            {"tx": "First Test Transcription", "tags": tag_name, "action": "Save"},
        )

        self.assertEqual(response.status_code, 200)

    def test_ConcordiaAssetView_get(self):
        """
        This unit test test the GET route /campaigns/<campaign>/asset/<Asset_name>/
        with already in use. Verify the updated_on time is updated on PageInUse
        """
        self.login_user()

        asset = create_asset()

        self.transcription = asset.transcription_set.create(
            user_id=self.user.id, text="Test transcription 1", status=Status.EDIT
        )
        self.transcription.save()

        url = "/campaigns/Campaign1/asset/Asset1/"

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

    def test_pageinuse_post(self):
        """
        Test the POST method on /campaigns/pageinuse/ route

        test that matching PageInUse entries with same page_url are deleted
        test that old entries in PageInUse table are removed
        """
        self.login_user()
        url = "example.com/bar"

        user2 = User.objects.create(username="tester2", email="tester2@example.com")
        user2.set_password("top_secret")
        user2.save()

        page1 = PageInUse(page_url=url, user=user2)
        page1.save()

        from datetime import datetime, timedelta

        time_threshold = datetime.now() - timedelta(minutes=20)

        # add two entries with old timestamps
        page2 = PageInUse(
            page_url="example.com/blah",
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

        response = self.client.post(
            "/campaigns/pageinuse/", {"page_url": url, "user": self.user}
        )

        self.assertEqual(response.status_code, 200)

    def test_project_detail_view(self):
        """
        Test GET on route /campaigns/<slug-value> (campaign)
        """
        project = create_project()

        response = self.client.get(
            "/campaigns/%s/%s/" % (project.campaign.slug, project.slug)
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="transcriptions/project.html")
