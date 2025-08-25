from unittest.mock import patch

from django.db.models.signals import post_save
from django.test import (
    TransactionTestCase,
    override_settings,
)
from django.urls import reverse
from django.utils.timezone import now

from concordia.models import (
    Transcription,
)
from concordia.signals.handlers import on_transcription_save
from concordia.utils import get_anonymous_user

from .utils import (
    CreateTestUsers,
    JSONAssertMixin,
    create_asset,
    create_campaign,
    create_item,
    create_project,
    create_topic,
)


@override_settings(
    RATELIMIT_ENABLE=False, SESSION_ENGINE="django.contrib.sessions.backends.cache"
)
class NextReviewableRedirectViewTests(
    CreateTestUsers, JSONAssertMixin, TransactionTestCase
):
    def test_find_next_reviewable_no_campaign(self):
        user = self.create_user("test-user")
        anon = get_anonymous_user()

        # Test case where there are no reviewable assets
        response = self.client.get(reverse("redirect-to-next-reviewable-asset"))
        self.assertRedirects(response, expected_url="/")

        asset1 = create_asset(slug="test-asset-1", title="Test Asset 1")
        asset2 = create_asset(
            item=asset1.item, slug="test-asset-2", title="Test Asset 2"
        )
        asset3 = create_asset(
            item=asset1.item, slug="test-asset-3", title="Test Asset 3"
        )
        campaign = asset1.item.project.campaign

        t1 = Transcription(asset=asset1, user=user, text="test", submitted=now())
        t1.full_clean()
        t1.save()

        t2 = Transcription(asset=asset2, user=anon, text="test", submitted=now())
        t2.full_clean()
        t2.save()

        t3 = Transcription(asset=asset3, user=anon, text="test", submitted=now())
        t3.full_clean()
        t3.save()

        response = self.client.get(reverse("redirect-to-next-reviewable-asset"))
        self.assertRedirects(response, expected_url=asset1.get_absolute_url())

        # Test logged in user (this creates a new user)
        # asset1 is no longer available due to the request above reserving it
        self.login_user()
        response = self.client.get(reverse("redirect-to-next-reviewable-asset"))
        self.assertRedirects(response, expected_url=asset2.get_absolute_url())

        # Configure campaign to be next review cmpaign for tests below
        campaign.next_review_campaign = True
        campaign.save()

        # Test when next reviewable campaign doesn't exist and there
        # are no other campaigns/assets
        with patch("concordia.models.Campaign.objects.get") as mock:
            mock.side_effect = IndexError
            response = self.client.get(reverse("redirect-to-next-reviewable-asset"))
        self.assertRedirects(response, expected_url="/")

        # Test case when a campaign is configured to be default next reviewable
        response = self.client.get(reverse("redirect-to-next-reviewable-asset"))
        self.assertRedirects(response, expected_url=asset3.get_absolute_url())

        # Test when next reviewable campaign has no reviewable assets
        asset1.delete()
        asset2.delete()
        response = self.client.get(reverse("redirect-to-next-reviewable-asset"))
        self.assertRedirects(response, expected_url="/")

        # Test when next reviewable campaign has no reviewable assets
        # and other campaigns exist and have no reviewable assets
        create_campaign(slug="test-campaign-2")
        response = self.client.get(reverse("redirect-to-next-reviewable-asset"))
        self.assertRedirects(response, expected_url="/")

    def test_find_next_reviewable_campaign(self):
        anon = get_anonymous_user()

        asset1 = create_asset(slug="test-review-asset-1", title="Test Asset 1")
        asset2 = create_asset(
            item=asset1.item, slug="test-review-asset-2", title="Test Asset 2"
        )

        t1 = Transcription(asset=asset1, user=anon, text="test", submitted=now())
        t1.full_clean()
        t1.save()

        t2 = Transcription(asset=asset2, user=anon, text="test", submitted=now())
        t2.full_clean()
        t2.save()

        campaign = asset1.item.project.campaign

        # Anonymous user test
        response = self.client.get(
            reverse(
                "transcriptions:redirect-to-next-reviewable-campaign-asset",
                kwargs={"campaign_slug": campaign.slug},
            )
        )
        self.assertRedirects(response, expected_url=asset1.get_absolute_url())

        # Authenticated user test
        # asset1 is no longer available since the previous request reserved it
        self.login_user()
        response = self.client.get(
            reverse(
                "transcriptions:redirect-to-next-reviewable-campaign-asset",
                kwargs={"campaign_slug": campaign.slug},
            )
        )
        self.assertRedirects(response, expected_url=asset2.get_absolute_url())

    def test_find_next_reviewable_topic(self):
        anon = get_anonymous_user()

        asset1 = create_asset(slug="test-review-asset-1")
        asset2 = create_asset(item=asset1.item, slug="test-review-asset-2")
        project = asset1.item.project
        topic = create_topic(project=project)

        t1 = Transcription(asset=asset1, user=anon, text="test", submitted=now())
        t1.full_clean()
        t1.save()

        t2 = Transcription(asset=asset2, user=anon, text="test", submitted=now())
        t2.full_clean()
        t2.save()

        # Anonymous user test
        response = self.client.get(
            reverse(
                "redirect-to-next-reviewable-topic-asset",
                kwargs={"topic_slug": topic.slug},
            )
        )
        self.assertRedirects(response, expected_url=asset1.get_absolute_url())

        # Authenticated user test
        # We expect that asset1 is no longer available. Even though
        # anonymous users can't reserve assets for review, we still will
        # have removed the asset from the NextReviewableTopicAsset table
        # to ensure two users don't receive the same asset
        self.login_user()
        response = self.client.get(
            reverse(
                "redirect-to-next-reviewable-topic-asset",
                kwargs={"topic_slug": topic.slug},
            )
        )
        self.assertRedirects(response, expected_url=asset2.get_absolute_url())

    def test_find_next_reviewable_unlisted_campaign(self):
        anon = get_anonymous_user()

        unlisted_campaign = create_campaign(
            slug="campaign-transcribe-redirect-unlisted",
            title="Test Unlisted Review Redirect Campaign",
            unlisted=True,
        )
        unlisted_project = create_project(
            title="Unlisted Project",
            slug="unlisted-project",
            campaign=unlisted_campaign,
        )
        unlisted_item = create_item(
            title="Unlisted Item",
            item_id="unlisted-item",
            item_url="https://blah.com/unlisted-item",
            project=unlisted_project,
        )

        asset1 = create_asset(slug="test-asset-1", item=unlisted_item)
        asset2 = create_asset(item=asset1.item, slug="test-asset-2")

        t1 = Transcription(asset=asset1, user=anon, text="test", submitted=now())
        t1.full_clean()
        t1.save()

        t2 = Transcription(asset=asset2, user=anon, text="test", submitted=now())
        t2.full_clean()
        t2.save()

        response = self.client.get(
            reverse(
                "transcriptions:redirect-to-next-reviewable-campaign-asset",
                kwargs={"campaign_slug": unlisted_campaign.slug},
            )
        )

        self.assertRedirects(response, expected_url=asset1.get_absolute_url())

    def tearDown(self):
        # We'll test the signal handler separately
        post_save.connect(on_transcription_save, sender=Transcription)
