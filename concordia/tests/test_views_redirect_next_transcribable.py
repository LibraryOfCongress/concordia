from unittest.mock import patch

from django.db.models.signals import post_save
from django.test import (
    TransactionTestCase,
    override_settings,
)
from django.urls import reverse

from concordia.models import (
    AssetTranscriptionReservation,
    Transcription,
    TranscriptionStatus,
)
from concordia.signals.handlers import on_transcription_save

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
class NextTranscribableRedirectViewTests(
    CreateTestUsers, JSONAssertMixin, TransactionTestCase
):
    def test_find_next_transcribable_no_campaign(self):
        # Test case where there are no transcribable assets
        resp = self.client.get(reverse("redirect-to-next-transcribable-asset"))
        self.assertRedirects(resp, expected_url="/")

        asset1 = create_asset(slug="test-asset-1")
        asset2 = create_asset(item=asset1.item, slug="test-asset-2")
        campaign = asset1.item.project.campaign

        resp = self.client.get(reverse("redirect-to-next-transcribable-asset"))
        self.assertRedirects(resp, expected_url=asset1.get_absolute_url())

        # Configure next transcription campaign for tests below
        campaign.next_transcription_campaign = True
        campaign.save()

        # Test when next transcribable campaign doesn't exist and there
        # are no other campaigns/assets
        with patch("concordia.models.Campaign.objects.get") as mock:
            mock.side_effect = IndexError
            response = self.client.get(reverse("redirect-to-next-transcribable-asset"))
        self.assertRedirects(response, expected_url="/")

        # Test case when a campaign is configured to be default next transcribable
        response = self.client.get(reverse("redirect-to-next-transcribable-asset"))
        self.assertRedirects(response, expected_url=asset2.get_absolute_url())

        # Test when next transcribable campaign has not transcribable assets
        asset1.delete()
        asset2.delete()
        response = self.client.get(reverse("redirect-to-next-transcribable-asset"))
        self.assertRedirects(response, expected_url="/")

        # Test when next transcription campaign has no transcribable assets
        # and other campaigns exist and have no transcribable assets
        create_campaign(slug="test-campaign-2")
        response = self.client.get(reverse("redirect-to-next-transcribable-asset"))
        self.assertRedirects(response, expected_url="/")

    def test_find_next_transcribable_campaign(self):
        asset1 = create_asset(slug="test-asset-1")
        asset2 = create_asset(item=asset1.item, slug="test-asset-2")
        campaign = asset1.item.project.campaign

        # Anonymous user test
        resp = self.client.get(
            reverse(
                "transcriptions:redirect-to-next-transcribable-campaign-asset",
                kwargs={"campaign_slug": campaign.slug},
            )
        )
        self.assertRedirects(resp, expected_url=asset1.get_absolute_url())

        # Authenticated user test
        self.login_user()
        resp = self.client.get(
            reverse(
                "transcriptions:redirect-to-next-transcribable-campaign-asset",
                kwargs={"campaign_slug": campaign.slug},
            )
        )
        self.assertRedirects(resp, expected_url=asset2.get_absolute_url())

    def test_find_next_transcribable_topic(self):
        asset1 = create_asset(slug="test-asset-1")
        asset2 = create_asset(item=asset1.item, slug="test-asset-2")
        project = asset1.item.project
        topic = create_topic(project=project)

        # Anonymous user test
        resp = self.client.get(
            reverse(
                "redirect-to-next-transcribable-topic-asset",
                kwargs={"topic_slug": topic.slug},
            )
        )
        self.assertRedirects(resp, expected_url=asset1.get_absolute_url())

        # Authenticated user test
        self.login_user()
        resp = self.client.get(
            reverse(
                "redirect-to-next-transcribable-topic-asset",
                kwargs={"topic_slug": topic.slug},
            )
        )
        self.assertRedirects(resp, expected_url=asset2.get_absolute_url())

    def test_find_next_transcribable_unlisted_campaign(self):
        unlisted_campaign = create_campaign(
            slug="campaign-transcribe-redirect-unlisted",
            title="Test Unlisted Transcribe Redirect Campaign",
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
        create_asset(item=asset1.item, slug="test-asset-2")

        response = self.client.get(
            reverse(
                "transcriptions:redirect-to-next-transcribable-campaign-asset",
                kwargs={"campaign_slug": unlisted_campaign.slug},
            )
        )

        self.assertRedirects(response, expected_url=asset1.get_absolute_url())

    def test_find_next_transcribable_single_asset(self):
        asset = create_asset()
        campaign = asset.item.project.campaign

        resp = self.client.get(
            reverse(
                "transcriptions:redirect-to-next-transcribable-campaign-asset",
                kwargs={"campaign_slug": campaign.slug},
            )
        )

        self.assertRedirects(resp, expected_url=asset.get_absolute_url())

    def test_find_next_transcribable_in_singleton_campaign(self):
        asset = create_asset(transcription_status=TranscriptionStatus.SUBMITTED)
        campaign = asset.item.project.campaign

        resp = self.client.get(
            reverse(
                "transcriptions:redirect-to-next-transcribable-campaign-asset",
                kwargs={"campaign_slug": campaign.slug},
            )
        )

        self.assertRedirects(resp, expected_url=reverse("homepage"))

    def test_find_next_transcribable_project_redirect(self):
        asset = create_asset(transcription_status=TranscriptionStatus.SUBMITTED)
        project = asset.item.project
        campaign = project.campaign

        resp = self.client.get(
            "%s?project=%s"
            % (
                reverse(
                    "transcriptions:redirect-to-next-transcribable-campaign-asset",
                    kwargs={"campaign_slug": campaign.slug},
                ),
                project.slug,
            )
        )

        self.assertRedirects(resp, expected_url=reverse("homepage"))

    def test_find_next_transcribable_hierarchy(self):
        """Confirm that find-next-page selects assets in the expected order"""

        asset = create_asset()
        item = asset.item
        project = item.project
        campaign = project.campaign

        asset_in_item = create_asset(item=item, slug="test-asset-in-same-item")
        in_progress_asset_in_item = create_asset(
            item=item,
            slug="inprogress-asset-in-same-item",
            transcription_status=TranscriptionStatus.IN_PROGRESS,
        )

        asset_in_project = create_asset(
            item=create_item(project=project, item_id="other-item-in-same-project"),
            title="test-asset-in-same-project",
        )

        asset_in_campaign = create_asset(
            item=create_item(
                project=create_project(campaign=campaign, title="other project"),
                title="item in other project",
            ),
            slug="test-asset-in-same-campaign",
        )

        # Now that we have test assets we'll see what find-next-page gives us as
        # successive test records are marked as submitted and thus ineligible.
        # The expected ordering is that it will favor moving forward (i.e. not
        # landing you on the same asset unless that's the only one available),
        # and will keep you closer to the asset you started from (i.e. within
        # the same item or project in that order).

        self.assertRedirects(
            self.client.get(
                reverse(
                    "transcriptions:redirect-to-next-transcribable-campaign-asset",
                    kwargs={"campaign_slug": campaign.slug},
                ),
                {"project": project.slug, "item": item.item_id, "asset": asset.pk},
            ),
            asset_in_item.get_absolute_url(),
        )

        asset_in_item.transcription_status = TranscriptionStatus.SUBMITTED
        asset_in_item.save()
        AssetTranscriptionReservation.objects.all().delete()

        self.assertRedirects(
            self.client.get(
                reverse(
                    "transcriptions:redirect-to-next-transcribable-campaign-asset",
                    kwargs={"campaign_slug": campaign.slug},
                ),
                {"project": project.slug, "item": item.item_id, "asset": asset.pk},
            ),
            asset_in_project.get_absolute_url(),
        )

        asset_in_project.transcription_status = TranscriptionStatus.SUBMITTED
        asset_in_project.save()
        AssetTranscriptionReservation.objects.all().delete()

        self.assertRedirects(
            self.client.get(
                reverse(
                    "transcriptions:redirect-to-next-transcribable-campaign-asset",
                    kwargs={"campaign_slug": campaign.slug},
                ),
                {"project": project.slug, "item": item.item_id, "asset": asset.pk},
            ),
            asset_in_campaign.get_absolute_url(),
        )

        asset_in_campaign.transcription_status = TranscriptionStatus.SUBMITTED
        asset_in_campaign.save()
        AssetTranscriptionReservation.objects.all().delete()

        self.assertRedirects(
            self.client.get(
                reverse(
                    "transcriptions:redirect-to-next-transcribable-campaign-asset",
                    kwargs={"campaign_slug": campaign.slug},
                ),
                {"project": project.slug, "item": item.item_id, "asset": asset.pk},
            ),
            in_progress_asset_in_item.get_absolute_url(),
        )

    def tearDown(self):
        # We'll test the signal handler separately
        post_save.connect(on_transcription_save, sender=Transcription)
