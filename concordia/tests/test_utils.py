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
from concordia.utils.next_asset.reviewable.campaign import (
    _eligible_reviewable_base_qs,
    _find_reviewable_in_item,
    _find_reviewable_in_project,
    _next_seq_after,
    _reserved_asset_ids_subq,
    find_and_order_potential_reviewable_campaign_assets,
    find_invalid_next_reviewable_campaign_assets,
)
from concordia.utils.next_asset.reviewable.topic import (
    _eligible_reviewable_base_qs as topic_eligible_reviewable_base_qs,
)
from concordia.utils.next_asset.reviewable.topic import (
    _find_reviewable_in_item as topic_find_reviewable_in_item,
)
from concordia.utils.next_asset.reviewable.topic import (
    _find_reviewable_in_project as topic_find_reviewable_in_project,
)
from concordia.utils.next_asset.reviewable.topic import (
    _next_seq_after as topic_next_seq_after,
)
from concordia.utils.next_asset.reviewable.topic import (
    _reserved_asset_ids_subq as topic_reserved_asset_ids_subq,
)
from concordia.utils.next_asset.reviewable.topic import (
    find_and_order_potential_reviewable_topic_assets,
    find_invalid_next_reviewable_topic_assets,
)
from concordia.utils.next_asset.reviewable.topic import (
    find_next_reviewable_topic_assets as find_cached_reviewable_topic_assets,
)

from .utils import (
    CreateTestUsers,
    create_asset,
    create_campaign,
    create_item,
    create_project,
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
        asset1 = self.asset1
        asset2 = self.asset2
        asset3 = create_asset(item=asset1.item, sequence=3, slug="rev-a3")
        for asset in (asset1, asset2, asset3):
            create_transcription(asset=asset, user=self.anon, submitted=now())

        # After asset1, pick asset2
        chosen = find_next_reviewable_campaign_asset(
            self.campaign,
            self.user,
            project_slug=asset1.item.project.slug,
            item_id=asset1.item.item_id,
            original_asset_id=asset1.id,
        )
        self.assertEqual(chosen, asset2)

        # Reserve asset2, so should pick asset3
        AssetTranscriptionReservation.objects.create(
            asset=asset2, reservation_token="rv"  # nosec
        )
        chosen2 = find_next_reviewable_campaign_asset(
            self.campaign,
            self.user,
            project_slug=asset1.item.project.slug,
            item_id=asset1.item.item_id,
            original_asset_id=asset1.id,
        )
        self.assertEqual(chosen2, asset3)

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
        project_asset = create_asset(item=other_item, slug="rev-p-asset")
        create_transcription(asset=project_asset, user=self.anon, submitted=now())

        chosen = find_next_reviewable_campaign_asset(
            self.campaign,
            self.user,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=self.asset1.id,
        )
        self.assertEqual(chosen, project_asset)

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

        # Pass empty project/item to ensure we hit cache (and thus spawn task)
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
        for asset in (self.asset1, self.asset2, asset3):
            create_transcription(asset=asset, user=self.anon, submitted=now())

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

    def test_find_next_reviewable_topic_assets_excludes_user(self):
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
        queryset = find_cached_reviewable_topic_assets(self.topic, self.user)
        self.assertNotIn(self.asset1.id, queryset.values_list("asset_id", flat=True))
        self.assertIn(self.asset2.id, queryset.values_list("asset_id", flat=True))

    @patch("concordia.utils.next_asset.reviewable.topic.get_registered_task")
    def test_next_reviewable_cached_path_when_short_circuits_fail_topic(
        self, mock_get_task
    ):
        """
        Item+project short-circuits fail (only user's work), so we should pull
        from the cached table and not spawn a task.
        """
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        # Only user's submitted work in current item/project
        create_transcription(asset=self.asset1, user=self.user, submitted=now())
        create_transcription(asset=self.asset2, user=self.user, submitted=now())

        # Cached eligible asset in another project (not reachable via short-circuit)
        cached_project = create_project(
            campaign=self.asset1.campaign,
            slug="topic-cached-proj",
            title="topic-cached-proj",
        )
        cached_item = create_item(project=cached_project, item_id="topic-cached-item")
        cached_asset = create_asset(item=cached_item, slug="topic-cached-asset")
        create_transcription(asset=cached_asset, user=self.anon, submitted=now())

        NextReviewableTopicAsset.objects.create(
            asset=cached_asset,
            topic=self.topic,
            item=cached_asset.item,
            item_item_id=cached_asset.item.item_id,
            project=cached_asset.item.project,
            project_slug=cached_asset.item.project.slug,
            sequence=cached_asset.sequence,
            transcriber_ids=[],
        )

        chosen = find_next_reviewable_topic_asset(
            self.topic,
            self.user,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=self.asset1.id,
        )
        self.assertEqual(chosen, cached_asset)
        self.assertFalse(mock_get_task.called)
        self.assertFalse(mock_task.delay.called)

    @patch("concordia.utils.next_asset.reviewable.topic.get_registered_task")
    def test_next_reviewable_uses_cache_when_bypassing_short_circuits_topic(
        self, mock_get_task
    ):
        """
        Pass blanks for project/item so we bypass short-circuits and hit cache.
        """
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        cached_project = create_project(
            campaign=self.asset1.campaign,
            slug="topic-cached-proj-2",
            title="topic-cached-proj-2",
        )
        cached_item = create_item(project=cached_project, item_id="topic-cached-item-2")
        cached_asset = create_asset(item=cached_item, slug="topic-cached-asset-2")
        create_transcription(asset=cached_asset, user=self.anon, submitted=now())

        NextReviewableTopicAsset.objects.create(
            asset=cached_asset,
            topic=self.topic,
            item=cached_asset.item,
            item_item_id=cached_asset.item.item_id,
            project=cached_asset.item.project,
            project_slug=cached_asset.item.project.slug,
            sequence=cached_asset.sequence,
            transcriber_ids=[],
        )

        chosen = find_next_reviewable_topic_asset(
            self.topic,
            self.user,
            project_slug="",
            item_id="",
            original_asset_id=None,
        )
        self.assertEqual(chosen, cached_asset)
        self.assertFalse(mock_get_task.called)
        self.assertFalse(mock_task.delay.called)

    @patch("concordia.utils.next_asset.reviewable.topic.get_registered_task")
    def test_next_reviewable_manual_fallback_no_after_spawns_and_picks_lowest_seq_topic(
        self, mock_get_task
    ):
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        other_item = create_item(project=self.asset1.item.project, item_id="t-mf-item")
        asset_x = create_asset(item=other_item, sequence=7, slug="t-mf-x")
        asset_y = create_asset(item=other_item, sequence=8, slug="t-mf-y")
        create_transcription(asset=asset_x, user=self.anon, submitted=now())
        create_transcription(asset=asset_y, user=self.anon, submitted=now())

        chosen = find_next_reviewable_topic_asset(
            self.topic,
            self.user,
            project_slug="",
            item_id="",
            original_asset_id=None,
        )
        self.assertEqual(chosen, asset_x)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    @patch("concordia.utils.next_asset.reviewable.topic.get_registered_task")
    def test_next_reviewable_manual_fallback_invalid_after_str_topic(
        self, mock_get_task
    ):
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        other_item = create_item(
            project=self.asset1.item.project, item_id="t-mf-item-2"
        )
        asset_a = create_asset(item=other_item, sequence=1, slug="t-mf-a")
        asset_b = create_asset(item=other_item, sequence=2, slug="t-mf-b")
        create_transcription(asset=asset_a, user=self.anon, submitted=now())
        create_transcription(asset=asset_b, user=self.anon, submitted=now())

        chosen = find_next_reviewable_topic_asset(
            self.topic,
            self.user,
            project_slug="",
            item_id="",
            original_asset_id="not-an-int",
        )
        self.assertEqual(chosen, asset_a)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)


class ReviewableTopicInternalsTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.anon = get_anonymous_user()
        self.user = self.create_test_user()
        self.asset1 = create_asset(sequence=1, slug="rt-a1")
        self.asset2 = create_asset(item=self.asset1.item, sequence=2, slug="rt-a2")
        self.topic = create_topic(project=self.asset1.item.project)

    def test_topic_reserved_asset_ids_subq_unfiltered(self):
        # Reservation tied to this test topic
        AssetTranscriptionReservation.objects.create(
            asset=self.asset1,
            reservation_token="rt-r1",  # nosec
        )
        # Reservation in entirely different campaign/project
        other_campaign = create_campaign(slug="rt-camp-x", title="rt-camp-x")
        other_project = create_project(
            campaign=other_campaign, slug="rt-proj-x", title="rt-proj-x"
        )
        other_item = create_item(project=other_project, item_id="rt-item-x")
        other_asset = create_asset(item=other_item, slug="rt-asset-x")
        AssetTranscriptionReservation.objects.create(
            asset=other_asset,
            reservation_token="rt-r2",  # nosec
        )

        reserved_ids = set(
            topic_reserved_asset_ids_subq().values_list("asset_id", flat=True)
        )
        self.assertIn(self.asset1.id, reserved_ids)
        self.assertIn(other_asset.id, reserved_ids)

    def test_topic_eligible_reviewable_base_qs_excludes_user_and_requires_submitted(
        self,
    ):
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        create_transcription(asset=self.asset2, user=self.user, submitted=now())
        asset3 = create_asset(item=self.asset1.item, sequence=3, slug="rt-a3")
        # asset3 has no submitted timestamp -> not SUBMITTED

        queryset_user = topic_eligible_reviewable_base_qs(self.topic, user=self.user)
        self.assertIn(self.asset1, queryset_user)
        self.assertNotIn(self.asset2, queryset_user)
        self.assertNotIn(asset3, queryset_user)

        queryset_none = topic_eligible_reviewable_base_qs(self.topic, user=None)
        self.assertIn(self.asset1, queryset_none)
        self.assertIn(self.asset2, queryset_none)
        self.assertNotIn(asset3, queryset_none)

    def test_topic_next_seq_after_none_missing_and_valid(self):
        self.assertIsNone(topic_next_seq_after(None))
        self.assertIsNone(topic_next_seq_after(987654321))
        self.assertEqual(topic_next_seq_after(self.asset2.pk), self.asset2.sequence)

    def test_topic_find_reviewable_in_item_after_none_returns_first(self):
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())

        chosen = topic_find_reviewable_in_item(
            self.topic,
            self.user,
            item_id=self.asset1.item.item_id,
            after_asset_pk=None,
        )
        self.assertEqual(chosen, self.asset1)

    def test_topic_find_reviewable_in_item_after_asset_in_other_item_ignores_gate(
        self,
    ):
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())

        other_item = create_item(
            project=self.asset1.item.project, item_id="rt-other-item"
        )
        other_asset = create_asset(item=other_item, slug="rt-other-asset")
        create_transcription(asset=other_asset, user=self.anon, submitted=now())

        chosen = topic_find_reviewable_in_item(
            self.topic,
            self.user,
            item_id=self.asset1.item.item_id,
            after_asset_pk=other_asset.id,
        )
        self.assertEqual(chosen, self.asset1)

    def test_topic_find_reviewable_in_item_after_asset_missing_ignores_gate(self):
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())

        chosen = topic_find_reviewable_in_item(
            self.topic,
            self.user,
            item_id=self.asset1.item.item_id,
            after_asset_pk=123456789,
        )
        self.assertEqual(chosen, self.asset1)

    def test_topic_find_reviewable_in_item_after_asset_sidc_ignores_gate(self):
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())

        other_campaign = create_campaign(slug="rt-camp-b", title="rt-camp-b")
        other_project = create_project(
            campaign=other_campaign, slug="rt-proj-b", title="rt-proj-b"
        )
        other_item = create_item(
            project=other_project, item_id=self.asset1.item.item_id
        )
        cross_asset = create_asset(item=other_item, slug="rt-cross")
        create_transcription(asset=cross_asset, user=self.anon, submitted=now())

        chosen = topic_find_reviewable_in_item(
            self.topic,
            self.user,
            item_id=self.asset1.item.item_id,
            after_asset_pk=cross_asset.id,
        )
        self.assertEqual(chosen, self.asset1)

    def test_topic_find_reviewable_in_project_orders_and_excludes_user(self):
        project = self.asset1.item.project
        other_item = create_item(project=project, item_id="rt-p-item")
        mine = create_asset(item=other_item, sequence=1, slug="rt-p-mine")
        theirs = create_asset(item=other_item, sequence=2, slug="rt-p-theirs")
        create_transcription(asset=mine, user=self.user, submitted=now())
        create_transcription(asset=theirs, user=self.anon, submitted=now())

        chosen = topic_find_reviewable_in_project(
            self.topic,
            self.user,
            project_slug=project.slug,
            after_asset_pk=self.asset1.id,
        )
        self.assertEqual(chosen, theirs)

    def test_topic_find_reviewable_in_project_returns_none_when_only_users_work(self):
        project = self.asset1.item.project
        other_item = create_item(project=project, item_id="rt-p2")
        mine = create_asset(item=other_item, sequence=1, slug="rt-p2-mine")
        create_transcription(asset=mine, user=self.user, submitted=now())

        chosen = topic_find_reviewable_in_project(
            self.topic,
            self.user,
            project_slug=project.slug,
            after_asset_pk=self.asset1.id,
        )
        self.assertIsNone(chosen)

    def test_find_and_order_potential_reviewable_topic_assets_ordering(self):
        base_item = self.asset1.item

        same_item_next = create_asset(item=base_item, sequence=10, slug="rt-ci-next")
        other_item_same_project = create_asset(
            item=create_item(project=base_item.project, item_id="rt-it-2"),
            sequence=5,
            slug="rt-p-next",
        )
        other_project = create_project(
            campaign=self.asset1.campaign, slug="rt-proj", title="rt-proj"
        )
        other_project_item = create_item(project=other_project, item_id="rt-it-3")
        other_project_asset = create_asset(
            item=other_project_item, sequence=1, slug="rt-op"
        )

        for asset in (same_item_next, other_item_same_project, other_project_asset):
            create_transcription(asset=asset, user=self.anon, submitted=now())
            NextReviewableTopicAsset.objects.create(
                asset=asset,
                topic=self.topic,
                item=asset.item,
                item_item_id=asset.item.item_id,
                project=asset.item.project,
                project_slug=asset.item.project.slug,
                sequence=asset.sequence,
                transcriber_ids=[],
            )

        ordered = find_and_order_potential_reviewable_topic_assets(
            self.topic,
            self.user,
            project_slug=base_item.project.slug,
            item_id=base_item.item_id,
            asset_pk=self.asset1.id,
        ).values_list("asset_id", flat=True)

        ordered = list(ordered)
        self.assertEqual(ordered[0], same_item_next.id)
        self.assertEqual(ordered[1], other_item_same_project.id)
        self.assertIn(other_project_asset.id, ordered[2:])

    def test_order_potential_without_after_prefers_item_then_project_topic(self):
        base_item = self.asset1.item

        same_item = create_asset(item=base_item, sequence=9, slug="rt-ci-none")
        same_project = create_asset(
            item=create_item(project=base_item.project, item_id="rt-it-np"),
            sequence=2,
            slug="rt-p-none",
        )
        other_project = create_project(
            campaign=self.asset1.campaign, slug="rt-proj-none", title="rt-proj-none"
        )
        other_project_item = create_item(project=other_project, item_id="rt-it-op-none")
        other_project_asset = create_asset(
            item=other_project_item, sequence=1, slug="rt-op-none"
        )
        for asset in (same_item, same_project, other_project_asset):
            create_transcription(asset=asset, user=self.anon, submitted=now())
            NextReviewableTopicAsset.objects.create(
                asset=asset,
                topic=self.topic,
                item=asset.item,
                item_item_id=asset.item.item_id,
                project=asset.item.project,
                project_slug=asset.item.project.slug,
                sequence=asset.sequence,
                transcriber_ids=[],
            )

        ordered = find_and_order_potential_reviewable_topic_assets(
            self.topic,
            self.user,
            project_slug=base_item.project.slug,
            item_id=base_item.item_id,
            asset_pk=None,  # next_asset==0 branch
        ).values_list("asset_id", flat=True)

        ordered = list(ordered)
        self.assertEqual(ordered[0], same_item.id)
        self.assertEqual(ordered[1], same_project.id)
        self.assertIn(other_project_asset.id, ordered[2:])

    def test_find_invalid_next_reviewable_topic_assets_reserved_and_wrong_status(
        self,
    ):
        # Reserved
        reserved_asset = create_asset(
            item=self.asset1.item, sequence=30, slug="rt-inv-res"
        )
        create_transcription(asset=reserved_asset, user=self.anon, submitted=now())
        AssetTranscriptionReservation.objects.create(
            asset=reserved_asset, reservation_token="rt-rv"  # nosec
        )
        NextReviewableTopicAsset.objects.create(
            asset=reserved_asset,
            topic=self.topic,
            item=reserved_asset.item,
            item_item_id=reserved_asset.item.item_id,
            project=reserved_asset.item.project,
            project_slug=reserved_asset.item.project.slug,
            sequence=reserved_asset.sequence,
            transcriber_ids=[],
        )

        # Wrong status (IN_PROGRESS)
        wrong_status_asset = create_asset(
            item=self.asset1.item, sequence=31, slug="rt-inv-wrong"
        )
        create_transcription(asset=wrong_status_asset, user=self.anon)
        NextReviewableTopicAsset.objects.create(
            asset=wrong_status_asset,
            topic=self.topic,
            item=wrong_status_asset.item,
            item_item_id=wrong_status_asset.item.item_id,
            project=wrong_status_asset.item.project,
            project_slug=wrong_status_asset.item.project.slug,
            sequence=wrong_status_asset.sequence,
            transcriber_ids=[],
        )

        invalid_ids = list(
            find_invalid_next_reviewable_topic_assets(self.topic.id).values_list(
                "asset_id", flat=True
            )
        )
        self.assertIn(reserved_asset.id, invalid_ids)
        self.assertIn(wrong_status_asset.id, invalid_ids)

    def test_topic_project_short_circuit_internal_skips_reserved_first(self):
        project = self.asset1.item.project
        item_two = create_item(project=project, item_id="rt-proj-int")
        first = create_asset(item=item_two, sequence=1, slug="rt-proj-int-1")
        second = create_asset(item=item_two, sequence=2, slug="rt-proj-int-2")
        for asset in (first, second):
            create_transcription(asset=asset, user=self.anon, submitted=now())
        AssetTranscriptionReservation.objects.create(
            asset=first, reservation_token="rt-proj-int"  # nosec
        )

        chosen = topic_find_reviewable_in_project(
            self.topic,
            self.user,
            project_slug=project.slug,
            after_asset_pk=self.asset1.id,
        )
        self.assertEqual(chosen, second)

    def test_topic_item_short_circuit_internal_excludes_users_own_work(self):
        mine = self.asset1
        other = self.asset2
        create_transcription(asset=mine, user=self.user, submitted=now())
        create_transcription(asset=other, user=self.anon, submitted=now())

        chosen = topic_find_reviewable_in_item(
            self.topic,
            self.user,
            item_id=mine.item.item_id,
            after_asset_pk=None,
        )
        self.assertEqual(chosen, other)

    def test_topic_item_short_circuit_internal_applies_after_and_skips_reserved(self):
        asset_three = create_asset(item=self.asset1.item, sequence=3, slug="rt-int-a3")
        for asset in (self.asset1, self.asset2, asset_three):
            create_transcription(asset=asset, user=self.anon, submitted=now())
        AssetTranscriptionReservation.objects.create(
            asset=self.asset2, reservation_token="rt-int-rv"  # nosec
        )

        chosen = topic_find_reviewable_in_item(
            self.topic,
            self.user,
            item_id=self.asset1.item.item_id,
            after_asset_pk=self.asset1.id,
        )
        self.assertEqual(chosen, asset_three)


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
        in_progress_asset = create_asset(
            item=other_item, slug="proj-inprog", title="Proj InProg"
        )
        create_transcription(asset=in_progress_asset, user=self.anon)  # IN_PROGRESS

        not_started_asset = create_asset(
            item=other_item, slug="proj-notstarted", title="Proj NotStarted"
        )

        chosen = find_next_transcribable_campaign_asset(
            self.campaign,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,  # same item, but it's exhausted
            original_asset_id=self.asset1.id,
        )
        self.assertEqual(chosen, not_started_asset)

    def test_project_short_circuit_when_item_id_empty_string(self):
        """
        If item_id is '', skip item short-circuit and use project-level.
        """
        other_item = create_item(project=self.asset1.item.project, item_id="proj2")
        project_asset = create_asset(
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
        self.assertEqual(chosen, project_asset)


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
        we_assert_in = self.assertIn  # readability alias to keep line length
        we_assert_in(self.asset2, queryset)

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
        in_progress = create_asset(
            item=other_item, sequence=1, slug="tproj-inprog", title="TProj InProg"
        )
        create_transcription(asset=in_progress, user=self.anon)

        not_started_asset = create_asset(
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
        self.assertEqual(chosen, not_started_asset)


class ReviewableCampaignInternalsTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.anon = get_anonymous_user()
        self.user = self.create_test_user()
        self.asset1 = create_asset(sequence=1, slug="rc-a1")
        # same item, higher sequence
        self.asset2 = create_asset(item=self.asset1.item, sequence=2, slug="rc-a2")
        self.campaign = self.asset1.campaign

    def test_reserved_asset_ids_subq_filters_to_campaign(self):
        # reservation in this campaign
        AssetTranscriptionReservation.objects.create(
            asset=self.asset1, reservation_token="r1"  # nosec
        )
        # reservation in a different campaign
        other_campaign = create_campaign(slug="rc-camp-a", title="rc-camp-a")
        other_project = create_project(
            campaign=other_campaign, slug="rc-proj-a", title="rc-proj-a"
        )
        other_item = create_item(project=other_project, item_id="rc-other-item")
        other_campaign_asset = create_asset(item=other_item, slug="rc-other-camp-a")
        AssetTranscriptionReservation.objects.create(
            asset=other_campaign_asset, reservation_token="r2"  # nosec
        )

        ids = set(
            _reserved_asset_ids_subq(self.campaign).values_list("asset_id", flat=True)
        )
        self.assertIn(self.asset1.id, ids)
        self.assertNotIn(other_campaign_asset.id, ids)

    def test_eligible_reviewable_base_qs_excludes_user_and_requires_submitted(self):
        # asset1 submitted by anon, asset2 submitted by self.user, asset3 not submitted
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        create_transcription(asset=self.asset2, user=self.user, submitted=now())
        asset3 = create_asset(item=self.asset1.item, sequence=3, slug="rc-a3")
        # no submitted timestamp => not SUBMITTED

        # With user filter: only anon-submitted should remain
        queryset_user = _eligible_reviewable_base_qs(self.campaign, user=self.user)
        self.assertIn(self.asset1, queryset_user)
        self.assertNotIn(self.asset2, queryset_user)
        self.assertNotIn(asset3, queryset_user)

        # Without user filter: both submitted should remain
        queryset_none = _eligible_reviewable_base_qs(self.campaign, user=None)
        self.assertIn(self.asset1, queryset_none)
        self.assertIn(self.asset2, queryset_none)
        self.assertNotIn(asset3, queryset_none)

    def test_next_seq_after_none_missing_and_valid(self):
        self.assertIsNone(_next_seq_after(None))
        self.assertIsNone(_next_seq_after(99999999))
        self.assertEqual(_next_seq_after(self.asset2.pk), self.asset2.sequence)

    def test_find_reviewable_in_item_after_none_returns_first(self):
        # both submitted by anon
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())

        chosen = _find_reviewable_in_item(
            self.campaign,
            self.user,
            item_id=self.asset1.item.item_id,
            after_asset_pk=None,
        )
        self.assertEqual(chosen, self.asset1)

    def test_find_reviewable_in_item_after_asset_in_other_item_ignores_gate(self):
        # make both eligible in the target item
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())

        # different item in same campaign
        other_item = create_item(
            project=self.asset1.item.project, item_id="rc-other-item"
        )
        other_asset = create_asset(item=other_item, slug="rc-other-asset")
        create_transcription(asset=other_asset, user=self.anon, submitted=now())

        # since after_asset_pk belongs to a different item, no sequence gate applied
        chosen = _find_reviewable_in_item(
            self.campaign,
            self.user,
            item_id=self.asset1.item.item_id,
            after_asset_pk=other_asset.id,
        )
        self.assertEqual(chosen, self.asset1)

    def test_find_reviewable_in_item_after_asset_missing_ignores_gate(self):
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())

        chosen = _find_reviewable_in_item(
            self.campaign,
            self.user,
            item_id=self.asset1.item.item_id,
            after_asset_pk=987654321,
        )
        self.assertEqual(chosen, self.asset1)

    def test_find_reviewable_in_item_after_asset_sidc_ignores_gate(self):
        # make the target item eligible
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())

        # create another campaign with an item of the same item_id
        other_campaign = create_campaign(slug="rc-camp-b", title="rc-camp-b")
        other_project = create_project(
            campaign=other_campaign, slug="rc-proj-b", title="rc-proj-b"
        )
        other_item = create_item(
            project=other_project, item_id=self.asset1.item.item_id
        )
        other_campaign_asset = create_asset(item=other_item, slug="rc-cross-camp")
        create_transcription(
            asset=other_campaign_asset, user=self.anon, submitted=now()
        )

        chosen = _find_reviewable_in_item(
            self.campaign,
            self.user,
            item_id=self.asset1.item.item_id,
            after_asset_pk=other_campaign_asset.id,
        )
        self.assertEqual(chosen, self.asset1)

    def test_find_reviewable_in_project_orders_and_excludes_user(self):
        # one submitted by user (exclude), one submitted by anon (eligible)
        other_item = create_item(project=self.asset1.item.project, item_id="rc-p-item")
        mine = create_asset(item=other_item, sequence=1, slug="rc-p-mine")
        theirs = create_asset(item=other_item, sequence=2, slug="rc-p-theirs")
        create_transcription(asset=mine, user=self.user, submitted=now())
        create_transcription(asset=theirs, user=self.anon, submitted=now())

        chosen = _find_reviewable_in_project(
            self.campaign,
            self.user,
            project_slug=self.asset1.item.project.slug,
            after_asset_pk=self.asset1.id,
        )
        self.assertEqual(chosen, theirs)

    def test_find_reviewable_in_project_returns_none_when_only_users_work(self):
        other_item = create_item(project=self.asset1.item.project, item_id="rc-p2")
        mine = create_asset(item=other_item, sequence=1, slug="rc-p2-mine")
        create_transcription(asset=mine, user=self.user, submitted=now())

        chosen = _find_reviewable_in_project(
            self.campaign,
            self.user,
            project_slug=self.asset1.item.project.slug,
            after_asset_pk=self.asset1.id,
        )
        self.assertIsNone(chosen)

    def test_find_new_reviewable_campaign_assets_excludes_reserved_and_next_table(self):
        asset_reserved = create_asset(
            item=self.asset1.item, sequence=3, slug="rc-a-res"
        )
        asset_cached = create_asset(
            item=self.asset1.item, sequence=4, slug="rc-a-cached"
        )
        for asset in (asset_reserved, asset_cached):
            create_transcription(asset=asset, user=self.anon, submitted=now())

        AssetTranscriptionReservation.objects.create(
            asset=asset_reserved, reservation_token="rv"  # nosec
        )

        from concordia.models import NextReviewableCampaignAsset

        NextReviewableCampaignAsset.objects.create(
            asset=asset_cached,
            campaign=self.campaign,
            item=asset_cached.item,
            item_item_id=asset_cached.item.item_id,
            project=asset_cached.item.project,
            project_slug=asset_cached.item.project.slug,
            sequence=asset_cached.sequence,
            transcriber_ids=[],
        )

        queryset = find_new_reviewable_campaign_assets(self.campaign, self.user)
        self.assertNotIn(asset_reserved, queryset)
        self.assertNotIn(asset_cached, queryset)

    def test_find_and_order_potential_reviewable_campaign_assets_ordering(self):
        # Build cache entries to assert ordering
        base_item = self.asset1.item

        same_item_next = create_asset(item=base_item, sequence=10, slug="rc-ci-next")

        other_item_same_project = create_asset(
            item=create_item(project=base_item.project, item_id="rc-it-2"),
            sequence=5,
            slug="rc-p-next",
        )

        # new project in same campaign
        other_project = create_project(
            campaign=self.campaign, slug="rc-proj", title="rc-proj"
        )
        other_project_item = create_item(project=other_project, item_id="rc-it-3")
        other_project_asset = create_asset(
            item=other_project_item, sequence=1, slug="rc-op"
        )

        for asset in (same_item_next, other_item_same_project, other_project_asset):
            create_transcription(asset=asset, user=self.anon, submitted=now())

        def cache_row(asset):
            return NextReviewableCampaignAsset.objects.create(
                asset=asset,
                campaign=self.campaign,
                item=asset.item,
                item_item_id=asset.item.item_id,
                project=asset.item.project,
                project_slug=asset.item.project.slug,
                sequence=asset.sequence,
                transcriber_ids=[],
            )

        cache_row(same_item_next)
        cache_row(other_item_same_project)
        cache_row(other_project_asset)

        after_primary_key = self.asset1.id

        ordered = find_and_order_potential_reviewable_campaign_assets(
            self.campaign,
            self.user,
            project_slug=base_item.project.slug,
            item_id=base_item.item_id,
            asset_pk=after_primary_key,
        ).values_list("asset_id", flat=True)

        ordered = list(ordered)
        self.assertEqual(ordered[0], same_item_next.id)
        self.assertEqual(ordered[1], other_item_same_project.id)
        self.assertIn(other_project_asset.id, ordered[2:])

    @patch("concordia.utils.next_asset.reviewable.campaign.get_registered_task")
    def test_find_reviewable_campaign_asset_no_eligible_spawns_task_and_returns_none(
        self, mock_get_task
    ):
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        # No SUBMITTED assets at all
        asset = find_reviewable_campaign_asset(self.campaign, self.user)
        self.assertIsNone(asset)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    @patch("concordia.utils.next_asset.reviewable.campaign.get_registered_task")
    def test_manual_fallback_orders_and_spawns_task(self, mock_get_task):
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        # two SUBMITTED assets; do not satisfy item/project short-circuits by passing
        # blanks
        asset_x = create_asset(item=self.asset1.item, sequence=7, slug="rc-mf-x")
        asset_y = create_asset(item=self.asset1.item, sequence=8, slug="rc-mf-y")
        create_transcription(asset=asset_x, user=self.anon, submitted=now())
        create_transcription(asset=asset_y, user=self.anon, submitted=now())

        chosen = find_next_reviewable_campaign_asset(
            self.campaign,
            self.user,
            project_slug="",
            item_id="",
            original_asset_id=asset_x.id,  # makes asset_y the "next" by id
        )
        self.assertEqual(chosen, asset_y)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    def test_find_invalid_next_reviewable_campaign_assets_reserved_and_wrong_status(
        self,
    ):
        from concordia.models import NextReviewableCampaignAsset

        # reserved
        reserved_asset = create_asset(
            item=self.asset1.item, sequence=30, slug="rc-inv-res"
        )
        create_transcription(asset=reserved_asset, user=self.anon, submitted=now())
        AssetTranscriptionReservation.objects.create(
            asset=reserved_asset, reservation_token="rv"  # nosec
        )
        NextReviewableCampaignAsset.objects.create(
            asset=reserved_asset,
            campaign=self.campaign,
            item=reserved_asset.item,
            item_item_id=reserved_asset.item.item_id,
            project=reserved_asset.item.project,
            project_slug=reserved_asset.item.project.slug,
            sequence=reserved_asset.sequence,
            transcriber_ids=[],
        )

        # wrong status (e.g., IN_PROGRESS)
        wrong_status_asset = create_asset(
            item=self.asset1.item, sequence=31, slug="rc-inv-wrong"
        )
        create_transcription(asset=wrong_status_asset, user=self.anon)  # IN_PROGRESS
        NextReviewableCampaignAsset.objects.create(
            asset=wrong_status_asset,
            campaign=self.campaign,
            item=wrong_status_asset.item,
            item_item_id=wrong_status_asset.item.item_id,
            project=wrong_status_asset.item.project,
            project_slug=wrong_status_asset.item.project.slug,
            sequence=wrong_status_asset.sequence,
            transcriber_ids=[],
        )

        invalid = list(
            find_invalid_next_reviewable_campaign_assets(self.campaign.id).values_list(
                "asset_id", flat=True
            )
        )
        self.assertIn(reserved_asset.id, invalid)
        self.assertIn(wrong_status_asset.id, invalid)

    def test_item_short_circuit_internal_applies_after_and_skips_reserved(self):
        # Same item, three SUBMITTED assets; reserve the middle one.
        asset1 = self.asset1
        asset2 = self.asset2
        asset3 = create_asset(item=asset1.item, sequence=3, slug="rc-int-a3")
        for asset in (asset1, asset2, asset3):
            create_transcription(asset=asset, user=self.anon, submitted=now())
        AssetTranscriptionReservation.objects.create(
            asset=asset2, reservation_token="rv-int"  # nosec
        )

        chosen = _find_reviewable_in_item(
            self.campaign,
            self.user,
            item_id=asset1.item.item_id,
            after_asset_pk=asset1.id,
        )
        # After asset1, asset2 is reserved, so asset3 should be chosen.
        self.assertEqual(chosen, asset3)

    def test_item_short_circuit_internal_excludes_users_own_work(self):
        # Same item, user's own SUBMITTED work should be excluded.
        mine = self.asset1
        other = self.asset2
        create_transcription(asset=mine, user=self.user, submitted=now())
        create_transcription(asset=other, user=self.anon, submitted=now())

        chosen = _find_reviewable_in_item(
            self.campaign,
            self.user,
            item_id=mine.item.item_id,
            after_asset_pk=None,
        )
        self.assertEqual(chosen, other)

    def test_project_short_circuit_internal_skips_reserved_first(self):
        # Two SUBMITTED in same project; reserve the earlier by sequence.
        project = self.asset1.item.project
        item2 = create_item(project=project, item_id="rc-proj-int")
        first = create_asset(item=item2, sequence=1, slug="rc-proj-int-1")
        second = create_asset(item=item2, sequence=2, slug="rc-proj-int-2")
        for asset in (first, second):
            create_transcription(asset=asset, user=self.anon, submitted=now())
        AssetTranscriptionReservation.objects.create(
            asset=first, reservation_token="rv-proj-int"  # nosec
        )

        chosen = _find_reviewable_in_project(
            self.campaign,
            self.user,
            project_slug=project.slug,
            after_asset_pk=self.asset1.id,
        )
        self.assertEqual(chosen, second)

    def test_order_potential_without_after_prefers_item_then_project(self):
        base_item = self.asset1.item

        same_item = create_asset(item=base_item, sequence=9, slug="rc-ci-none")
        same_project = create_asset(
            item=create_item(project=base_item.project, item_id="rc-it-np"),
            sequence=2,
            slug="rc-p-none",
        )
        other_project = create_asset(
            item=create_item(
                project=create_project(
                    campaign=self.campaign, slug="rc-proj-none", title="rc-proj-none"
                ),
                item_id="rc-it-op-none",
            ),
            sequence=1,
            slug="rc-op-none",
        )
        for asset in (same_item, same_project, other_project):
            create_transcription(asset=asset, user=self.anon, submitted=now())

        # Cache rows (no user in transcriber_ids).
        NextReviewableCampaignAsset.objects.create(
            asset=same_item,
            campaign=self.campaign,
            item=same_item.item,
            item_item_id=same_item.item.item_id,
            project=same_item.item.project,
            project_slug=same_item.item.project.slug,
            sequence=same_item.sequence,
            transcriber_ids=[],
        )
        NextReviewableCampaignAsset.objects.create(
            asset=same_project,
            campaign=self.campaign,
            item=same_project.item,
            item_item_id=same_project.item.item_id,
            project=same_project.item.project,
            project_slug=same_project.item.project.slug,
            sequence=same_project.sequence,
            transcriber_ids=[],
        )
        NextReviewableCampaignAsset.objects.create(
            asset=other_project,
            campaign=self.campaign,
            item=other_project.item,
            item_item_id=other_project.item.item_id,
            project=other_project.item.project,
            project_slug=other_project.item.project.slug,
            sequence=other_project.sequence,
            transcriber_ids=[],
        )

        ordered = find_and_order_potential_reviewable_campaign_assets(
            self.campaign,
            self.user,
            project_slug=base_item.project.slug,
            item_id=base_item.item_id,
            asset_pk=None,  # ensure next_asset==0
        ).values_list("asset_id", flat=True)

        ordered = list(ordered)
        # same_item (same project+item) first, then same project, then other proj
        self.assertEqual(ordered[0], same_item.id)
        self.assertEqual(ordered[1], same_project.id)
        self.assertIn(other_project.id, ordered[2:])

    @patch("concordia.utils.next_asset.reviewable.campaign.get_registered_task")
    def test_next_reviewable_manual_fallback_no_after_spawns_and_picks_lowest_seq(
        self, mock_get_task
    ):
        # No cache hits, no item/project short-circuit, no after id -> sequence order.
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        asset1 = self.asset1
        asset2 = self.asset2
        create_transcription(asset=asset1, user=self.anon, submitted=now())
        create_transcription(asset=asset2, user=self.anon, submitted=now())

        chosen = find_next_reviewable_campaign_asset(
            self.campaign,
            self.user,
            project_slug="",
            item_id="",
            original_asset_id=None,  # triggers Value(0) annotation branch
        )
        self.assertEqual(chosen, asset1)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    @patch("concordia.utils.next_asset.reviewable.campaign.get_registered_task")
    def test_next_reviewable_manual_fallback_invalid_after_str(self, mock_get_task):
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        asset1 = self.asset1
        asset2 = self.asset2
        create_transcription(asset=asset1, user=self.anon, submitted=now())
        create_transcription(asset=asset2, user=self.anon, submitted=now())

        chosen = find_next_reviewable_campaign_asset(
            self.campaign,
            self.user,
            project_slug="",
            item_id="",
            original_asset_id="not-an-int",
        )
        self.assertEqual(chosen, asset1)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    @patch("concordia.utils.next_asset.reviewable.campaign.get_registered_task")
    def test_next_reviewable_cached_path_when_short_circuits_fail(self, mock_get_task):
        """
        Provide item_id and project_slug so short-circuits run but fail
        (only user's SUBMITTED work in that scope), then ensure we use
        the cached table (no task spawned).
        """
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        # Item-level and project-level have only user's SUBMITTED assets.
        create_transcription(asset=self.asset1, user=self.user, submitted=now())
        create_transcription(asset=self.asset2, user=self.user, submitted=now())

        # Cached eligible asset in another project within same campaign.
        cached_project = create_project(
            campaign=self.campaign, slug="rc-cached-proj", title="rc-cached-proj"
        )
        cached_item = create_item(project=cached_project, item_id="rc-cached-item")
        cached_asset = create_asset(item=cached_item, slug="rc-cached-asset")
        create_transcription(asset=cached_asset, user=self.anon, submitted=now())

        NextReviewableCampaignAsset.objects.create(
            asset=cached_asset,
            campaign=self.campaign,
            item=cached_asset.item,
            item_item_id=cached_asset.item.item_id,
            project=cached_asset.item.project,
            project_slug=cached_asset.item.project.slug,
            sequence=cached_asset.sequence,
            transcriber_ids=[],
        )

        chosen = find_next_reviewable_campaign_asset(
            self.campaign,
            self.user,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=self.asset1.id,
        )
        self.assertEqual(chosen, cached_asset)
        self.assertFalse(mock_get_task.called)
        self.assertFalse(mock_task.delay.called)

    @patch("concordia.utils.next_asset.reviewable.campaign.get_registered_task")
    def test_next_reviewable_uses_cache_when_bypassing_short_circuits(
        self, mock_get_task
    ):
        """
        Skip both short-circuits by passing blanks; ensure we return from
        the cache table directly (no task spawned).
        """
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        cached_project = create_project(
            campaign=self.campaign,
            slug="rc-cached-proj-2",
            title="rc-cached-proj-2",
        )
        cached_item = create_item(project=cached_project, item_id="rc-cached-item-2")
        cached_asset = create_asset(item=cached_item, slug="rc-cached-asset-2")
        create_transcription(asset=cached_asset, user=self.anon, submitted=now())

        NextReviewableCampaignAsset.objects.create(
            asset=cached_asset,
            campaign=self.campaign,
            item=cached_asset.item,
            item_item_id=cached_asset.item.item_id,
            project=cached_asset.item.project,
            project_slug=cached_asset.item.project.slug,
            sequence=cached_asset.sequence,
            transcriber_ids=[],
        )

        chosen = find_next_reviewable_campaign_asset(
            self.campaign,
            self.user,
            project_slug="",
            item_id="",
            original_asset_id=None,
        )
        self.assertEqual(chosen, cached_asset)
        self.assertFalse(mock_get_task.called)
        self.assertFalse(mock_task.delay.called)


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
