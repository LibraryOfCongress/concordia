from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils.timezone import now

from concordia.models import (
    AssetTranscriptionReservation,
    NextReviewableCampaignAsset,
)
from concordia.utils import get_anonymous_user
from concordia.utils.next_asset import (
    find_new_reviewable_campaign_assets,
    find_next_reviewable_campaign_asset,
    find_reviewable_campaign_asset,
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

from .utils import (
    CreateTestUsers,
    create_asset,
    create_campaign,
    create_item,
    create_project,
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


class ReviewableCampaignInternalsTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.anon = get_anonymous_user()
        self.user = self.create_test_user()
        self.asset1 = create_asset(sequence=1, slug="rc-a1")
        # same item, higher sequence
        self.asset2 = create_asset(item=self.asset1.item, sequence=2, slug="rc-a2")
        self.campaign = self.asset1.campaign

    def test_reserved_asset_ids_subq_filters_to_campaign(self):
        AssetTranscriptionReservation.objects.create(
            asset=self.asset1, reservation_token="r1"  # nosec
        )
        other_campaign = create_campaign(slug="rc-camp-a", title="rc-camp-a")
        other_project = create_project(
            campaign=other_campaign, slug="rc-proj-a", title="rc-proj-a"
        )
        other_item = create_item(project=other_project, item_id="rc-other-item")
        other_campaign_asset = create_asset(item=other_item, slug="rc-other-camp-a")
        AssetTranscriptionReservation.objects.create(
            asset=other_campaign_asset, reservation_token="r2"  # nosec
        )

        id_set = set(
            _reserved_asset_ids_subq(self.campaign).values_list("asset_id", flat=True)
        )
        self.assertIn(self.asset1.id, id_set)
        self.assertNotIn(other_campaign_asset.id, id_set)

    def test_eligible_reviewable_base_qs_excludes_user_and_requires_submitted(self):
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        create_transcription(asset=self.asset2, user=self.user, submitted=now())
        asset3 = create_asset(item=self.asset1.item, sequence=3, slug="rc-a3")

        queryset_user = _eligible_reviewable_base_qs(self.campaign, user=self.user)
        self.assertIn(self.asset1, queryset_user)
        self.assertNotIn(self.asset2, queryset_user)
        self.assertNotIn(asset3, queryset_user)

        queryset_none = _eligible_reviewable_base_qs(self.campaign, user=None)
        self.assertIn(self.asset1, queryset_none)
        self.assertIn(self.asset2, queryset_none)
        self.assertNotIn(asset3, queryset_none)

    def test_next_seq_after_none_missing_and_valid(self):
        self.assertIsNone(_next_seq_after(None))
        self.assertIsNone(_next_seq_after(99999999))
        self.assertEqual(_next_seq_after(self.asset2.pk), self.asset2.sequence)

    def test_find_reviewable_in_item_after_none_returns_first(self):
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
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())

        other_item = create_item(
            project=self.asset1.item.project, item_id="rc-other-item"
        )
        other_asset = create_asset(item=other_item, slug="rc-other-asset")
        create_transcription(asset=other_asset, user=self.anon, submitted=now())

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
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())

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

    def test_find_new_reviewable_campaign_assets_excludes_reserved_and_next_table(
        self,
    ):
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
        base_item = self.asset1.item

        same_item_next = create_asset(item=base_item, sequence=10, slug="rc-ci-next")

        other_item_same_project = create_asset(
            item=create_item(project=base_item.project, item_id="rc-it-2"),
            sequence=5,
            slug="rc-p-next",
        )

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

        asset = find_reviewable_campaign_asset(self.campaign, self.user)
        self.assertIsNone(asset)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    @patch("concordia.utils.next_asset.reviewable.campaign.get_registered_task")
    def test_manual_fallback_orders_and_spawns_task(self, mock_get_task):
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

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
        self.assertEqual(chosen, asset3)

    def test_item_short_circuit_internal_excludes_users_own_work(self):
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
        self.assertEqual(ordered[0], same_item.id)
        self.assertEqual(ordered[1], same_project.id)
        self.assertIn(other_project.id, ordered[2:])

    @patch("concordia.utils.next_asset.reviewable.campaign.get_registered_task")
    def test_next_reviewable_manual_fallback_no_after_spawns_and_picks_lowest_seq(
        self, mock_get_task
    ):
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

        create_transcription(asset=self.asset1, user=self.user, submitted=now())
        create_transcription(asset=self.asset2, user=self.user, submitted=now())

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
