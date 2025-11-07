from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils.timezone import now

from concordia.models import (
    AssetTranscriptionReservation,
    NextReviewableTopicAsset,
)
from concordia.utils import get_anonymous_user
from concordia.utils.next_asset import (
    find_new_reviewable_topic_assets,
    find_next_reviewable_topic_asset,
    find_reviewable_topic_asset,
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

        id_set = set(topic_reserved_asset_ids_subq().values_list("asset_id", flat=True))
        self.assertIn(self.asset1.id, id_set)
        self.assertIn(other_asset.id, id_set)

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
        item2 = create_item(project=project, item_id="rt-proj-int")
        first = create_asset(item=item2, sequence=1, slug="rt-proj-int-1")
        second = create_asset(item=item2, sequence=2, slug="rt-proj-int-2")
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
        asset3 = create_asset(item=self.asset1.item, sequence=3, slug="rt-int-a3")
        for asset in (self.asset1, self.asset2, asset3):
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
        self.assertEqual(chosen, asset3)
