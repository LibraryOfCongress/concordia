from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils.timezone import now

from concordia.models import (
    NextReviewableCampaignAsset,
)
from concordia.utils import get_anonymous_user
from concordia.utils.next_asset import (
    find_new_reviewable_campaign_assets,
    find_next_reviewable_campaign_asset,
    find_reviewable_campaign_asset,
)

from .utils import CreateTestUsers, create_asset, create_transcription


class NextReviewableCampaignAssetTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.anon = get_anonymous_user()
        self.user = self.create_test_user()
        self.asset1 = create_asset()
        self.asset2 = create_asset(item=self.asset1.item, slug="test-asset-2")
        self.campaign = self.asset1.campaign

    def test_find_new_reviewable_campaign_assets_filters_correctly(self):
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())

        queryset = find_new_reviewable_campaign_assets(self.campaign, self.user)
        self.assertIn(self.asset1, queryset)

    def test_find_new_reviewable_campaign_assets_without_user(self):
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        # Covers lines 28–30
        queryset = find_new_reviewable_campaign_assets(self.campaign, None)
        self.assertIn(self.asset1, queryset)

    def test_find_reviewable_campaign_asset_from_next_table(self):
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())

        NextReviewableCampaignAsset.objects.create(
            asset=self.asset1,
            campaign=self.campaign,
            item=self.asset1.item,
            item_item_id=self.asset1.item.item_id,
            project=self.asset1.item.project,
            project_slug=self.asset1.item.project.slug,
            sequence=self.asset1.sequence,
            transcriber_ids=[],
        )

        asset = find_reviewable_campaign_asset(self.campaign, self.user)
        self.assertEqual(asset, self.asset1)

    @patch("concordia.utils.next_asset.reviewable.campaign.get_registered_task")
    def test_find_reviewable_campaign_asset_falls_back_and_spawns_task(
        self, mock_get_task
    ):
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        asset = find_reviewable_campaign_asset(self.campaign, self.user)
        self.assertEqual(asset, self.asset2)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    @patch("concordia.utils.next_asset.reviewable.campaign.get_registered_task")
    def test_find_next_reviewable_campaign_asset_orders_and_falls_back(
        self, mock_get_task
    ):
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        asset = find_next_reviewable_campaign_asset(
            self.campaign,
            self.user,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=self.asset1.id,
        )
        self.assertEqual(asset, self.asset1)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    @patch("concordia.utils.next_asset.reviewable.campaign.get_registered_task")
    def test_find_next_reviewable_campaign_asset_when_next_asset_exists(
        self, mock_get_task
    ):
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        NextReviewableCampaignAsset.objects.create(
            asset=self.asset2,
            campaign=self.campaign,
            item=self.asset2.item,
            item_item_id=self.asset2.item.item_id,
            project=self.asset2.item.project,
            project_slug=self.asset2.item.project.slug,
            sequence=self.asset2.sequence,
            transcriber_ids=[],
        )

        asset = find_next_reviewable_campaign_asset(
            self.campaign,
            self.user,
            project_slug=self.asset2.item.project.slug,
            item_id=self.asset2.item.item_id,
            original_asset_id=self.asset2.id - 1,
        )
        self.assertEqual(asset, self.asset2)
        self.assertFalse(mock_get_task.called)
        self.assertFalse(mock_task.delay.called)
