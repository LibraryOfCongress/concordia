from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils.timezone import now

from concordia.logging import get_logging_user_id
from concordia.models import (
    AssetTranscriptionReservation,
    NextReviewableCampaignAsset,
    NextReviewableTopicAsset,
    NextTranscribableCampaignAsset,
    NextTranscribableTopicAsset,
    TranscriptionStatus,
)
from concordia.utils import get_anonymous_user
from concordia.utils.next_asset import (
    find_new_reviewable_campaign_assets,
    find_new_reviewable_topic_assets,
    find_new_transcribable_campaign_assets,
    find_new_transcribable_topic_assets,
    find_next_reviewable_campaign_asset,
    find_next_reviewable_topic_asset,
    find_next_transcribable_campaign_asset,
    find_next_transcribable_topic_asset,
    find_reviewable_campaign_asset,
    find_reviewable_topic_asset,
    find_transcribable_campaign_asset,
    find_transcribable_topic_asset,
)

from .utils import (
    CreateTestUsers,
    create_asset,
    create_item,
    create_topic,
    create_transcription,
)


class NextReviewableCampaignAssetTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.anon = get_anonymous_user()
        self.user = self.create_test_user()
        self.asset1 = create_asset(sequence=1)
        self.asset2 = create_asset(
            item=self.asset1.item, sequence=2, slug="test-asset-2"
        )
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
        """
        With short-circuiting: project-level returns the eligible asset
        and we do not spawn a task.
        """
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
        # Short-circuit satisfied -> no cache fallback -> no task spawned
        self.assertFalse(mock_get_task.called)
        self.assertFalse(mock_task.delay.called)

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

    def test_short_circuit_same_item_excludes_users_own_work(self):
        """
        Reviewable item short-circuit must not return assets
        transcribed by the requesting user.
        """
        # Two submitted in same item: one by self.user, one by anon
        mine = self.asset1
        other = self.asset2
        create_transcription(asset=mine, user=self.user, submitted=now())
        create_transcription(asset=other, user=self.anon, submitted=now())

        chosen = find_next_reviewable_campaign_asset(
            self.campaign,
            self.user,
            project_slug=mine.item.project.slug,
            item_id=mine.item.item_id,
            original_asset_id=mine.id,
        )
        self.assertEqual(chosen, other)

    def test_item_short_circuit_reviewable_respects_after_sequence_and_reservations(
        self,
    ):
        """
        Item reviewable short-circuit should choose next by sequence
        and skip reserved assets.
        """
        # Three submitted in the same item (none by self.user)
        a1 = self.asset1
        a2 = self.asset2
        a3 = create_asset(item=a1.item, sequence=3, slug="rev-a3")
        for a in (a1, a2, a3):
            create_transcription(asset=a, user=self.anon, submitted=now())

        # After a1, pick a2
        chosen = find_next_reviewable_campaign_asset(
            self.campaign,
            self.user,
            project_slug=a1.item.project.slug,
            item_id=a1.item.item_id,
            original_asset_id=a1.id,
        )
        self.assertEqual(chosen, a2)

        # Reserve a2, so should pick a3
        AssetTranscriptionReservation.objects.create(
            asset=a2, reservation_token="rv"  # nosec
        )
        chosen2 = find_next_reviewable_campaign_asset(
            self.campaign,
            self.user,
            project_slug=a1.item.project.slug,
            item_id=a1.item.item_id,
            original_asset_id=a1.id,
        )
        self.assertEqual(chosen2, a3)

    def test_project_short_circuit_when_item_has_only_users_work(self):
        """
        If the only SUBMITTED assets in the item were transcribed by the user,
        the function should fall back to other assets in the same project.
        """
        # Item-level: only user's work
        create_transcription(asset=self.asset1, user=self.user, submitted=now())
        create_transcription(asset=self.asset2, user=self.user, submitted=now())

        # Project-level: someone else's work
        other_item = create_item(project=self.asset1.item.project, item_id="p2")
        proj_asset = create_asset(item=other_item, slug="rev-p-asset")
        create_transcription(asset=proj_asset, user=self.anon, submitted=now())

        chosen = find_next_reviewable_campaign_asset(
            self.campaign,
            self.user,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=self.asset1.id,
        )
        self.assertEqual(chosen, proj_asset)

    @patch("concordia.utils.next_asset.reviewable.campaign.get_registered_task")
    def test_cache_excludes_user_and_triggers_spawn_task(self, mock_get_task):
        """
        When the only cached asset is excluded via transcriber_ids containing the user,
        the function should skip cache, fall back to manual and spawn a populate task.
        """
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        # Cached entry references the user's own work (excluded by contains)
        create_transcription(asset=self.asset1, user=self.user, submitted=now())
        NextReviewableCampaignAsset.objects.create(
            asset=self.asset1,
            campaign=self.campaign,
            item=self.asset1.item,
            item_item_id=self.asset1.item.item_id,
            project=self.asset1.item.project,
            project_slug=self.asset1.item.project.slug,
            sequence=self.asset1.sequence,
            transcriber_ids=[self.user.id],
        )

        # A valid reviewable exists elsewhere
        other = create_asset(item=self.asset1.item, sequence=3, slug="rev-other")
        create_transcription(asset=other, user=self.anon, submitted=now())

        # Pass empty project/item to ensure we hit cache path (and thus spawn task)
        chosen = find_next_reviewable_campaign_asset(
            self.campaign,
            self.user,
            project_slug="",
            item_id="",
            original_asset_id=None,
        )
        self.assertEqual(chosen, other)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)


class NextReviewableTopicAssetTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.anon = get_anonymous_user()
        self.user = self.create_test_user()
        self.asset1 = create_asset(sequence=1)
        self.asset2 = create_asset(
            item=self.asset1.item, sequence=2, slug="test-asset-2"
        )
        self.topic = create_topic(project=self.asset1.item.project)

    def test_find_new_reviewable_topic_assets_filters_correctly(self):
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())

        queryset = find_new_reviewable_topic_assets(self.topic, self.user)
        self.assertIn(self.asset1, queryset)

    def test_find_new_reviewable_topic_assets_without_user(self):
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())

        queryset = find_new_reviewable_topic_assets(self.topic, None)
        self.assertIn(self.asset1, queryset)

    def test_find_reviewable_topic_asset_from_next_table(self):
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())

        NextReviewableTopicAsset.objects.create(
            asset=self.asset1,
            topic=self.topic,
            item=self.asset1.item,
            item_item_id=self.asset1.item.item_id,
            project=self.asset1.item.project,
            project_slug=self.asset1.item.project.slug,
            sequence=self.asset1.sequence,
            transcriber_ids=[],
        )

        asset = find_reviewable_topic_asset(self.topic, self.user)
        self.assertEqual(asset, self.asset1)

    @patch("concordia.utils.next_asset.reviewable.topic.get_registered_task")
    def test_find_reviewable_topic_asset_falls_back_and_spawns_task(
        self, mock_get_task
    ):
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        asset = find_reviewable_topic_asset(self.topic, self.user)
        self.assertEqual(asset, self.asset2)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    @patch("concordia.utils.next_asset.reviewable.topic.get_registered_task")
    def test_find_next_reviewable_topic_asset_orders_and_falls_back(
        self, mock_get_task
    ):
        """
        With short-circuiting: project-level returns
        the eligible asset and we do not spawn a task.
        """
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        asset = find_next_reviewable_topic_asset(
            self.topic,
            self.user,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=self.asset1.id,
        )
        self.assertEqual(asset, self.asset1)
        # Short-circuit satisfied -> no cache fallback -> no task spawned
        self.assertFalse(mock_get_task.called)
        self.assertFalse(mock_task.delay.called)

    @patch("concordia.utils.next_asset.reviewable.topic.get_registered_task")
    def test_find_next_reviewable_topic_asset_when_next_asset_exists(
        self, mock_get_task
    ):
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        NextReviewableTopicAsset.objects.create(
            asset=self.asset2,
            topic=self.topic,
            item=self.asset2.item,
            item_item_id=self.asset2.item.item_id,
            project=self.asset2.item.project,
            project_slug=self.asset2.item.project.slug,
            sequence=self.asset2.sequence,
            transcriber_ids=[],
        )

        asset = find_next_reviewable_topic_asset(
            self.topic,
            self.user,
            project_slug=self.asset2.item.project.slug,
            item_id=self.asset2.item.item_id,
            original_asset_id=self.asset2.id - 1,
        )
        self.assertEqual(asset, self.asset2)
        self.assertFalse(mock_get_task.called)
        self.assertFalse(mock_task.delay.called)

    def test_short_circuit_same_item_topic_excludes_users_own_work(self):
        mine = self.asset1
        other = self.asset2
        create_transcription(asset=mine, user=self.user, submitted=now())
        create_transcription(asset=other, user=self.anon, submitted=now())

        chosen = find_next_reviewable_topic_asset(
            self.topic,
            self.user,
            project_slug=mine.item.project.slug,
            item_id=mine.item.item_id,
            original_asset_id=mine.id,
        )
        self.assertEqual(chosen, other)

    def test_item_short_circuit_topic_reviewable_respects_after_and_reservations(self):
        asset3 = create_asset(item=self.asset1.item, sequence=3, slug="rev-topic-a3")
        for a in (self.asset1, self.asset2, asset3):
            create_transcription(asset=a, user=self.anon, submitted=now())

        chosen = find_next_reviewable_topic_asset(
            self.topic,
            self.user,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=self.asset1.id,
        )
        self.assertEqual(chosen, self.asset2)

        AssetTranscriptionReservation.objects.create(
            asset=self.asset2, reservation_token="rv"  # nosec
        )
        chosen2 = find_next_reviewable_topic_asset(
            self.topic,
            self.user,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=self.asset1.id,
        )
        self.assertEqual(chosen2, asset3)

    @patch("concordia.utils.next_asset.reviewable.topic.get_registered_task")
    def test_cache_excludes_user_and_triggers_spawn_task_topic(self, mock_get_task):
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        create_transcription(asset=self.asset1, user=self.user, submitted=now())
        NextReviewableTopicAsset.objects.create(
            asset=self.asset1,
            topic=self.topic,
            item=self.asset1.item,
            item_item_id=self.asset1.item.item_id,
            project=self.asset1.item.project,
            project_slug=self.asset1.item.project.slug,
            sequence=self.asset1.sequence,
            transcriber_ids=[self.user.id],
        )

        other = create_asset(item=self.asset1.item, sequence=3, slug="rev-topic-other")
        create_transcription(asset=other, user=self.anon, submitted=now())

        chosen = find_next_reviewable_topic_asset(
            self.topic,
            self.user,
            project_slug="",
            item_id="",
            original_asset_id=None,
        )
        self.assertEqual(chosen, other)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)


class NextTranscribableCampaignAssetTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.anon = get_anonymous_user()
        self.user = self.create_test_user()
        self.asset1 = create_asset(
            sequence=1, slug="test-asset-1", title="Test Asset 1"
        )
        self.asset2 = create_asset(
            item=self.asset1.item, sequence=2, slug="test-asset-2", title="Test Asset 2"
        )
        self.campaign = self.asset1.campaign

    def test_find_new_transcribable_campaign_assets_filters_correctly(self):
        create_transcription(
            asset=self.asset1,
            user=self.anon,
            submitted=now(),
        )

        queryset = find_new_transcribable_campaign_assets(self.campaign)
        self.assertNotIn(self.asset1, queryset)
        self.assertIn(self.asset2, queryset)

    def test_find_transcribable_campaign_asset_from_next_table(self):
        NextTranscribableCampaignAsset.objects.create(
            asset=self.asset1,
            campaign=self.campaign,
            item=self.asset1.item,
            item_item_id=self.asset1.item.item_id,
            project=self.asset1.item.project,
            project_slug=self.asset1.item.project.slug,
            sequence=self.asset1.sequence,
            transcription_status=TranscriptionStatus.NOT_STARTED,
        )

        asset = find_transcribable_campaign_asset(self.campaign)
        self.assertEqual(asset, self.asset1)

    @patch("concordia.utils.next_asset.transcribable.campaign.get_registered_task")
    def test_find_transcribable_campaign_asset_falls_back_and_spawns_task(
        self, mock_get_task
    ):
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        asset = find_transcribable_campaign_asset(self.campaign)
        self.assertEqual(asset, self.asset1)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    @patch("concordia.utils.next_asset.transcribable.campaign.get_registered_task")
    def test_find_next_transcribable_campaign_asset_orders_and_falls_back(
        self, mock_get_task
    ):
        """
        With short-circuiting: item-level returns the next asset
        and we do not spawn a task.
        """
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        asset = find_next_transcribable_campaign_asset(
            self.campaign,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=self.asset1.id,
        )
        self.assertEqual(asset, self.asset2)
        # Short-circuit satisfied -> no cache fallback -> no task spawned
        self.assertFalse(mock_get_task.called)
        self.assertFalse(mock_task.delay.called)

    @patch("concordia.utils.next_asset.transcribable.campaign.get_registered_task")
    def test_find_next_transcribable_campaign_asset_when_next_asset_exists(
        self, mock_get_task
    ):
        # Make asset2 eligible (IN_PROGRESS)
        create_transcription(
            asset=self.asset2,
            user=self.anon,
        )
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        # Cache has asset2
        NextTranscribableCampaignAsset.objects.create(
            asset=self.asset2,
            campaign=self.campaign,
            item=self.asset2.item,
            item_item_id=self.asset2.item.item_id,
            project=self.asset2.item.project,
            project_slug=self.asset2.item.project.slug,
            sequence=self.asset2.sequence,
            transcription_status=TranscriptionStatus.IN_PROGRESS,
        )

        # Bypass item/project short-circuits so we hit the cache
        asset = find_next_transcribable_campaign_asset(
            self.campaign,
            project_slug="",
            item_id="",
            original_asset_id=None,
        )
        self.assertEqual(asset, self.asset2)
        self.assertFalse(mock_get_task.called)
        self.assertFalse(mock_task.delay.called)

    def test_short_circuit_same_item_respects_after_sequence_and_reservations(self):
        """
        Same item short-circuit:
        - Picks the next by sequence (> original)
        - Skips reserved assets
        """
        # asset1 is seqence=1 and asset2 is seqence=2 under the same item
        # We want a third in the same item to verify skip on reservation.
        asset3 = create_asset(
            item=self.asset1.item, sequence=3, slug="test-asset-3", title="Test Asset 3"
        )

        # Normal: after asset1 => choose asset2
        chosen = find_next_transcribable_campaign_asset(
            self.campaign,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=self.asset1.id,
        )
        self.assertEqual(chosen, self.asset2)

        # Reserve asset2 => should skip to asset3
        AssetTranscriptionReservation.objects.create(
            asset=self.asset2, reservation_token="tkn"  # nosec
        )
        chosen2 = find_next_transcribable_campaign_asset(
            self.campaign,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=self.asset1.id,
        )
        self.assertEqual(chosen2, asset3)

    def test_project_short_circuit_prefers_not_started_over_in_progress(self):
        """
        When item-level has no eligible assets, project-level should:
        - Prefer NOT_STARTED over IN_PROGRESS
        - Order by (item_id, sequence) within same status
        """
        # Exhaust item: mark both item assets submitted
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())

        other_item = create_item(
            project=self.asset1.item.project, item_id="proj-only-item"
        )
        in_prog = create_asset(item=other_item, slug="proj-inprog", title="Proj InProg")
        create_transcription(asset=in_prog, user=self.anon)  # IN_PROGRESS

        not_started = create_asset(
            item=other_item, slug="proj-notstarted", title="Proj NotStarted"
        )

        chosen = find_next_transcribable_campaign_asset(
            self.campaign,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,  # same item, but it's exhausted
            original_asset_id=self.asset1.id,
        )
        self.assertEqual(chosen, not_started)

    def test_project_short_circuit_when_item_id_empty_string(self):
        """
        If item_id is '', skip item short-circuit and use project-level.
        """
        other_item = create_item(project=self.asset1.item.project, item_id="proj2")
        proj_asset = create_asset(
            item=other_item, slug="proj-asset", title="Proj Asset"
        )
        # Make current item ineligible
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())

        chosen = find_next_transcribable_campaign_asset(
            self.campaign,
            project_slug=self.asset1.item.project.slug,
            item_id="",  # empty skips item short-circuit
            original_asset_id=self.asset1.id,
        )
        self.assertEqual(chosen, proj_asset)


class NextTranscribableTopicAssetTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.anon = get_anonymous_user()
        self.user = self.create_test_user()
        self.asset1 = create_asset(
            slug="topic-asset-1", sequence=1, title="Topic Asset 1"
        )
        self.asset2 = create_asset(
            item=self.asset1.item,
            sequence=2,
            slug="topic-asset-2",
            title="Topic Asset 2",
        )
        self.topic = create_topic(project=self.asset1.item.project)

    def test_find_new_transcribable_topic_assets_filters_correctly(self):
        create_transcription(
            asset=self.asset1,
            user=self.anon,
            submitted=now(),
        )

        queryset = find_new_transcribable_topic_assets(self.topic)
        self.assertNotIn(self.asset1, queryset)
        self.assertIn(self.asset2, queryset)

    def test_find_transcribable_topic_asset_from_next_table(self):
        NextTranscribableTopicAsset.objects.create(
            asset=self.asset1,
            topic=self.topic,
            item=self.asset1.item,
            item_item_id=self.asset1.item.item_id,
            project=self.asset1.item.project,
            project_slug=self.asset1.item.project.slug,
            sequence=self.asset1.sequence,
            transcription_status=TranscriptionStatus.NOT_STARTED,
        )

        asset = find_transcribable_topic_asset(self.topic)
        self.assertEqual(asset, self.asset1)

    @patch("concordia.utils.next_asset.transcribable.topic.get_registered_task")
    def test_find_transcribable_topic_asset_falls_back_and_spawns_task(
        self, mock_get_task
    ):
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        asset = find_transcribable_topic_asset(self.topic)
        self.assertEqual(asset, self.asset1)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    @patch("concordia.utils.next_asset.transcribable.topic.get_registered_task")
    def test_find_next_transcribable_topic_asset_orders_and_falls_back(
        self, mock_get_task
    ):
        """
        With short-circuiting: item-level returns the next asset
        and we do not spawn a task.
        """
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        asset = find_next_transcribable_topic_asset(
            self.topic,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=self.asset1.id,
        )
        self.assertEqual(asset, self.asset2)
        # Short-circuit satisfied -> no cache fallback -> no task spawned
        self.assertFalse(mock_get_task.called)
        self.assertFalse(mock_task.delay.called)

    @patch("concordia.utils.next_asset.transcribable.topic.get_registered_task")
    def test_find_next_transcribable_topic_asset_when_next_asset_exists(
        self, mock_get_task
    ):
        create_transcription(asset=self.asset2, user=self.anon)
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        NextTranscribableTopicAsset.objects.create(
            asset=self.asset2,
            topic=self.topic,
            item=self.asset2.item,
            item_item_id=self.asset2.item.item_id,
            project=self.asset2.item.project,
            project_slug=self.asset2.item.project.slug,
            sequence=self.asset2.sequence,
            transcription_status=TranscriptionStatus.IN_PROGRESS,
        )

        asset = find_next_transcribable_topic_asset(
            self.topic,
            project_slug="",
            item_id="",
            original_asset_id=None,
        )
        self.assertEqual(asset, self.asset2)
        self.assertFalse(mock_get_task.called)
        self.assertFalse(mock_task.delay.called)

    def test_short_circuit_same_item_topic_respects_after_sequence_and_reservations(
        self,
    ):
        third = create_asset(
            item=self.asset1.item,
            sequence=3,
            slug="topic-asset-3",
            title="Topic Asset 3",
        )

        chosen = find_next_transcribable_topic_asset(
            self.topic,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=self.asset1.id,
        )
        self.assertEqual(chosen, self.asset2)

        AssetTranscriptionReservation.objects.create(
            asset=self.asset2, reservation_token="tkn"  # nosec
        )
        chosen2 = find_next_transcribable_topic_asset(
            self.topic,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=self.asset1.id,
        )
        self.assertEqual(chosen2, third)

    def test_project_short_circuit_topic_prefers_not_started_over_in_progress(self):
        # Exhaust item
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())

        other_item = create_item(project=self.asset1.item.project, item_id="tproj-item")
        in_prog = create_asset(
            item=other_item, sequence=1, slug="tproj-inprog", title="TProj InProg"
        )
        create_transcription(asset=in_prog, user=self.anon)

        not_started = create_asset(
            item=other_item,
            sequence=2,
            slug="tproj-notstarted",
            title="TProj NotStarted",
        )

        chosen = find_next_transcribable_topic_asset(
            self.topic,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=self.asset1.id,
        )
        self.assertEqual(chosen, not_started)


class LoggingTests(CreateTestUsers, TestCase):
    def test_get_logging_user_id_authenticated_user(self):
        user = self.create_test_user()
        self.assertEqual(get_logging_user_id(user), str(user.id))

    def test_get_logging_user_id_anonymous_user(self):
        anon = get_anonymous_user()
        self.assertEqual(get_logging_user_id(anon), "anonymous")

    def test_get_logging_user_id_missing_auth_attribute(self):
        # Simulate a user-like object with no is_authenticated attribute
        mock_user = object()
        # Should fallback to "anonymous" since getattr will not find .is_authenticated
        self.assertEqual(get_logging_user_id(mock_user), "anonymous")

    def test_get_logging_user_id_authenticated_no_id(self):
        user = SimpleNamespace(is_authenticated=True, username="someuser")
        # Intentionally omit 'id' to trigger the final check
        self.assertEqual(get_logging_user_id(user), "anonymous")
