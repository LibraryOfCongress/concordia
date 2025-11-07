from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils.timezone import now

from concordia.models import (
    Asset,
    AssetTranscriptionReservation,
    NextTranscribableCampaignAsset,
    TranscriptionStatus,
)
from concordia.utils import get_anonymous_user
from concordia.utils.next_asset import (
    find_new_transcribable_campaign_assets,
    find_next_transcribable_campaign_asset,
    find_transcribable_campaign_asset,
)
from concordia.utils.next_asset.transcribable.campaign import (
    _eligible_transcribable_base_qs as tc_eligible_base_qs,
)
from concordia.utils.next_asset.transcribable.campaign import (
    _find_transcribable_in_item as tc_find_in_item,
)
from concordia.utils.next_asset.transcribable.campaign import (
    _find_transcribable_not_started_in_project as tc_find_ns_in_proj,
)
from concordia.utils.next_asset.transcribable.campaign import (
    _next_seq_after as tc_next_seq_after,
)
from concordia.utils.next_asset.transcribable.campaign import (
    _order_unstarted_first as tc_order_unstarted_first,
)
from concordia.utils.next_asset.transcribable.campaign import (
    _reserved_asset_ids_subq as tc_reserved_ids_subq,
)
from concordia.utils.next_asset.transcribable.campaign import (
    find_and_order_potential_transcribable_campaign_assets,
    find_invalid_next_transcribable_campaign_assets,
)
from concordia.utils.next_asset.transcribable.campaign import (
    find_next_transcribable_campaign_assets as find_cached_transcribable_assets,
)

from .utils import (
    CreateTestUsers,
    create_asset,
    create_campaign,
    create_item,
    create_project,
    create_transcription,
)


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

    @patch("concordia.utils.next_asset.transcribable.campaign.get_registered_task")
    def test_find_transcribable_campaign_asset_none_spawns(self, mock_get_task):
        """
        When no NOT_STARTED/IN_PROGRESS exist, return None and trigger populate.
        """
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()
        # Make both assets SUBMITTED (no transcribable remain)
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())

        asset = find_transcribable_campaign_asset(self.campaign)
        self.assertIsNone(asset)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    @patch("concordia.utils.next_asset.transcribable.campaign.get_registered_task")
    def test_next_transcribable_manual_no_after_prefers_not_started(
        self, mock_get_task
    ):
        """
        With no short-circuit and empty cache, pick NOT_STARTED and spawn task.
        """
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        campaign2 = create_campaign(slug="tc-na-camp", title="tc-na-camp")
        project2 = create_project(
            campaign=campaign2, slug="tc-na-proj", title="tc-na-proj"
        )
        item2 = create_item(project=project2, item_id="tc-na-item")

        not_started_asset = create_asset(
            item=item2, sequence=2, slug="tc-na-ns", title="TC NA NS"
        )
        in_progress_asset = create_asset(
            item=item2, sequence=1, slug="tc-na-ip", title="TC NA IP"
        )
        create_transcription(asset=in_progress_asset, user=self.anon)  # IN_PROGRESS

        chosen = find_next_transcribable_campaign_asset(
            campaign2, project_slug="", item_id="", original_asset_id=None
        )
        self.assertEqual(chosen, not_started_asset)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    @patch("concordia.utils.next_asset.transcribable.campaign.get_registered_task")
    def test_next_transcribable_manual_invalid_after_str(self, mock_get_task):
        """
        Treat a non-integer "after" like None: choose NOT_STARTED and spawn task.
        """
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        # Make existing setup assets ineligible for selection.
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())

        other_item = create_item(
            project=self.asset1.item.project, item_id="tc-mf-item-2"
        )
        asset_a = create_asset(
            item=other_item, sequence=1, slug="tc-mf-a", title="TC MF A"
        )
        asset_b = create_asset(
            item=other_item, sequence=2, slug="tc-mf-b", title="TC MF B"
        )
        create_transcription(asset=asset_b, user=self.anon)  # IN_PROGRESS

        chosen = find_next_transcribable_campaign_asset(
            self.campaign, project_slug="", item_id="", original_asset_id=None
        )
        self.assertEqual(chosen, asset_a)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    @patch("concordia.utils.next_asset.transcribable.campaign.get_registered_task")
    def test_next_transcribable_none_anywhere_spawns(self, mock_get_task):
        """
        With no cache and no manual candidates: return None; do not spawn a task.
        """
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        campaign2 = create_campaign(slug="tc-none-camp", title="tc-none-camp")

        chosen = find_next_transcribable_campaign_asset(
            campaign2, project_slug="", item_id="", original_asset_id=None
        )
        self.assertIsNone(chosen)
        self.assertFalse(mock_get_task.called)
        self.assertFalse(mock_task.delay.called)

    def test_item_short_circuit_missing_after_pk_treated_as_none_top(self):
        # Both assets are NOT_STARTED in the same item. Give a missing "after".
        missing_pk = 987_654_321
        chosen = find_next_transcribable_campaign_asset(
            self.campaign,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=missing_pk,
        )
        # With no valid "after" seq, returns the first NOT_STARTED (asset1).
        self.assertEqual(chosen, self.asset1)

    @patch("concordia.utils.next_asset.transcribable.campaign.get_registered_task")
    def test_cache_excludes_original_pk_and_chooses_next(self, mock_get_task):
        # Two cached rows; original points at the first -> second should be chosen.
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        other_item = create_item(
            project=self.asset1.item.project, item_id="tc-cache-pk-item"
        )
        first = create_asset(item=other_item, sequence=1, slug="tc-cache-first")
        second = create_asset(item=other_item, sequence=2, slug="tc-cache-second")

        for asset in (first, second):
            NextTranscribableCampaignAsset.objects.create(
                asset=asset,
                campaign=self.campaign,
                item=asset.item,
                item_item_id=asset.item.item_id,
                project=asset.item.project,
                project_slug=asset.item.project.slug,
                sequence=asset.sequence,
                transcription_status=TranscriptionStatus.NOT_STARTED,
            )

        chosen = find_next_transcribable_campaign_asset(
            self.campaign,
            project_slug="",
            item_id="",
            original_asset_id=first.id,
        )
        self.assertEqual(chosen, second)
        self.assertFalse(mock_get_task.called)
        self.assertFalse(mock_task.delay.called)

    def test_project_short_circuit_without_original_id(self):
        # Exhaust current item; ensure project-level returns NOT_STARTED with
        # original_asset_id=None.
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())

        other_item = create_item(
            project=self.asset1.item.project, item_id="tc-proj-no-orig"
        )
        pick = create_asset(item=other_item, sequence=5, slug="tc-proj-pick")

        chosen = find_next_transcribable_campaign_asset(
            self.campaign,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=None,
        )
        self.assertEqual(chosen, pick)

    def test_item_short_circuit_after_pk_in_other_item_ignores_gate(self):
        # Original PK exists but belongs to a different item; treat as no "after".
        other_item = create_item(
            project=self.asset1.item.project, item_id="tc-oth-it-ignores-gate"
        )
        other_asset = create_asset(item=other_item, slug="tc-oth-a-ignores-gate")

        chosen = find_next_transcribable_campaign_asset(
            self.campaign,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=other_asset.id,
        )
        # With no valid "after" in this item, pick first NOT_STARTED by sequence.
        self.assertEqual(chosen, self.asset1)

    def test_next_transcribable_after_pk_missing_treats_as_no_after(self):
        """
        Missing original_asset_id -> ignore 'after' gate and pick first NS in item.
        """
        chosen = find_next_transcribable_campaign_asset(
            self.campaign,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=987654321,  # missing
        )
        self.assertEqual(chosen, self.asset1)

    @patch("concordia.utils.next_asset.transcribable.campaign.get_registered_task")
    def test_no_ns_anywhere_and_no_ip_in_item_returns_none(self, mock_get_task):
        """
        With item_id present: no NOT_STARTED anywhere and no same-item IN_PROGRESS
        so return None and do not spawn a task.
        """
        # Exhaust the only item in the project/campaign.
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())

        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        got = find_next_transcribable_campaign_asset(
            self.campaign,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=self.asset1.id,
        )
        self.assertIsNone(got)
        self.assertFalse(mock_get_task.called)
        self.assertFalse(mock_task.delay.called)

    def test_after_pk_digit_string_missing_treats_as_no_after(self):
        """
        original_asset_id is a digit string for a missing PK -> treat like no 'after'.
        Covers the DoesNotExist branch distinct from non-digit ValueError.
        """
        chosen = find_next_transcribable_campaign_asset(
            self.campaign,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id="987654321",  # digit string, no such Asset
        )
        self.assertEqual(chosen, self.asset1)

    def test_same_item_inprogress_selected_when_no_ns_and_no_after(self):
        """
        With item_id present, no NOT_STARTED anywhere and original_asset_id=None,
        pick same-item IN_PROGRESS (after_seq is None path).
        """
        create_transcription(asset=self.asset2, user=self.anon)  # IN_PROGRESS
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())

        got = find_next_transcribable_campaign_asset(
            self.campaign,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=None,  # after_seq is None in IP fallback
        )
        self.assertEqual(got, self.asset2)

    @patch("concordia.utils.next_asset.transcribable.campaign.get_registered_task")
    def test_manual_invalid_after_str_campaign_valueerror_branch(self, mock_get_task):
        """
        original_asset_id is a non-digit string -> ValueError path.
        Bypass short-circuits and empty cache => manual picks first NOT_STARTED
        and spawns populate task.
        """
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        chosen = find_next_transcribable_campaign_asset(
            self.campaign,
            project_slug="",
            item_id="",
            original_asset_id="not-an-int",
        )
        self.assertEqual(chosen, self.asset1)  # first NOT_STARTED by ordering
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)


class TranscribableCampaignInternalsTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.anon = get_anonymous_user()
        self.user = self.create_test_user()
        self.asset1 = create_asset(sequence=1, slug="tc-a1")
        self.asset2 = create_asset(item=self.asset1.item, sequence=2, slug="tc-a2")
        self.campaign = self.asset1.campaign

    def test_new_transcribable_excludes_reserved_and_cached(self):
        reserved_asset = create_asset(item=self.asset1.item, sequence=3, slug="tc-res")
        cached_asset = create_asset(item=self.asset1.item, sequence=4, slug="tc-cached")
        # Make both potentially transcribable
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())
        # Reserve one and cache the other
        AssetTranscriptionReservation.objects.create(
            asset=reserved_asset, reservation_token="tc-rv"  # nosec
        )
        NextTranscribableCampaignAsset.objects.create(
            asset=cached_asset,
            campaign=self.campaign,
            item=cached_asset.item,
            item_item_id=cached_asset.item.item_id,
            project=cached_asset.item.project,
            project_slug=cached_asset.item.project.slug,
            sequence=cached_asset.sequence,
            transcription_status=TranscriptionStatus.NOT_STARTED,
        )
        queryset = find_new_transcribable_campaign_assets(self.campaign)
        self.assertNotIn(reserved_asset, queryset)
        self.assertNotIn(cached_asset, queryset)

    def test_order_potential_transcribable_pref(self):
        """
        Cached ordering should favor next id, then same project, then same item.
        """
        base_item = self.asset1.item
        same_item_next = create_asset(item=base_item, sequence=10, slug="tc-ci-next")
        same_project = create_asset(
            item=create_item(project=base_item.project, item_id="tc-it-2"),
            sequence=5,
            slug="tc-p-next",
        )
        other_project_asset = create_asset(
            item=create_item(
                project=create_project(
                    campaign=self.campaign, slug="tc-op-proj", title="tc-op-proj"
                ),
                item_id="tc-op-item",
            ),
            sequence=1,
            slug="tc-op",
        )
        for asset in (same_item_next, same_project, other_project_asset):
            NextTranscribableCampaignAsset.objects.create(
                asset=asset,
                campaign=self.campaign,
                item=asset.item,
                item_item_id=asset.item.item_id,
                project=asset.item.project,
                project_slug=asset.item.project.slug,
                sequence=asset.sequence,
                transcription_status=TranscriptionStatus.NOT_STARTED,
            )
        ordered = find_and_order_potential_transcribable_campaign_assets(
            self.campaign,
            project_slug=base_item.project.slug,
            item_id=base_item.item_id,
            asset_pk=self.asset1.id,
        ).values_list("asset_id", flat=True)
        ordered = list(ordered)
        self.assertEqual(ordered[0], same_item_next.id)
        self.assertEqual(ordered[1], same_project.id)
        self.assertIn(other_project_asset.id, ordered[2:])

    def test_order_potential_transcribable_no_after(self):
        """
        With no 'after', prefer same item, then same project.
        """
        base_item = self.asset1.item
        same_item = create_asset(item=base_item, sequence=9, slug="tc-ci-none")
        same_project = create_asset(
            item=create_item(project=base_item.project, item_id="tc-it-np"),
            sequence=2,
            slug="tc-p-none",
        )
        other_project_asset = create_asset(
            item=create_item(
                project=create_project(
                    campaign=self.campaign, slug="tc-proj-none", title="tc-proj-none"
                ),
                item_id="tc-it-op-none",
            ),
            sequence=1,
            slug="tc-op-none",
        )
        for asset in (same_item, same_project, other_project_asset):
            NextTranscribableCampaignAsset.objects.create(
                asset=asset,
                campaign=self.campaign,
                item=asset.item,
                item_item_id=asset.item.item_id,
                project=asset.item.project,
                project_slug=asset.item.project.slug,
                sequence=asset.sequence,
                transcription_status=TranscriptionStatus.NOT_STARTED,
            )
        ordered = find_and_order_potential_transcribable_campaign_assets(
            self.campaign,
            project_slug=base_item.project.slug,
            item_id=base_item.item_id,
            asset_pk=None,
        ).values_list("asset_id", flat=True)
        ordered = list(ordered)
        self.assertEqual(ordered[0], same_item.id)
        self.assertEqual(ordered[1], same_project.id)
        self.assertIn(other_project_asset.id, ordered[2:])

    def test_invalid_next_transcribable_reserved_and_submitted(self):
        """
        Invalid cache rows include reserved or SUBMITTED assets.
        """
        reserved_asset = create_asset(
            item=self.asset1.item, sequence=30, slug="tc-inv-res"
        )
        AssetTranscriptionReservation.objects.create(
            asset=reserved_asset, reservation_token="tc-rv-2"  # nosec
        )
        NextTranscribableCampaignAsset.objects.create(
            asset=reserved_asset,
            campaign=self.campaign,
            item=reserved_asset.item,
            item_item_id=reserved_asset.item.item_id,
            project=reserved_asset.item.project,
            project_slug=reserved_asset.item.project.slug,
            sequence=reserved_asset.sequence,
            transcription_status=TranscriptionStatus.NOT_STARTED,
        )
        wrong_status_asset = create_asset(
            item=self.asset1.item, sequence=31, slug="tc-inv-wrong"
        )
        create_transcription(asset=wrong_status_asset, user=self.anon, submitted=now())
        NextTranscribableCampaignAsset.objects.create(
            asset=wrong_status_asset,
            campaign=self.campaign,
            item=wrong_status_asset.item,
            item_item_id=wrong_status_asset.item.item_id,
            project=wrong_status_asset.item.project,
            project_slug=wrong_status_asset.item.project.slug,
            sequence=wrong_status_asset.sequence,
            transcription_status=TranscriptionStatus.NOT_STARTED,
        )
        bad = list(
            find_invalid_next_transcribable_campaign_assets(
                self.campaign.id
            ).values_list("asset_id", flat=True)
        )
        self.assertIn(reserved_asset.id, bad)
        self.assertIn(wrong_status_asset.id, bad)


class TranscribableCampaignMoreInternalsTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.anon = get_anonymous_user()
        self.user = self.create_test_user()
        self.asset1 = create_asset(sequence=1, slug="tc-more-a1", title="TC More A1")
        self.asset2 = create_asset(
            item=self.asset1.item, sequence=2, slug="tc-more-a2", title="TC More A2"
        )
        self.campaign = self.asset1.campaign

    def test_tc_reserved_ids_filters_to_campaign(self):
        AssetTranscriptionReservation.objects.create(
            asset=self.asset1, reservation_token="tc-res-here"  # nosec
        )
        other_campaign = create_campaign(slug="tc-other-c", title="tc-other-c")
        other_project = create_project(
            campaign=other_campaign, slug="tc-other-p", title="tc-other-p"
        )
        other_item = create_item(project=other_project, item_id="tc-other-it")
        other_asset = create_asset(item=other_item, slug="tc-other-a")
        AssetTranscriptionReservation.objects.create(
            asset=other_asset, reservation_token="tc-res-there"  # nosec
        )

        id_set = set(
            tc_reserved_ids_subq(self.campaign).values_list("asset_id", flat=True)
        )
        self.assertIn(self.asset1.id, id_set)
        self.assertNotIn(other_asset.id, id_set)

    def test_tc_next_seq_after_variants(self):
        self.assertIsNone(tc_next_seq_after(None))
        self.assertIsNone(tc_next_seq_after(999_999_999))
        self.assertEqual(tc_next_seq_after(self.asset2.id), self.asset2.sequence)

    def test_tc_order_unstarted_first_prefers_not_started(self):
        create_transcription(asset=self.asset2, user=self.anon)
        queryset = Asset.objects.filter(id__in=[self.asset1.id, self.asset2.id])
        ordered = list(tc_order_unstarted_first(queryset).values_list("id", flat=True))
        self.assertEqual(ordered[0], self.asset1.id)
        self.assertEqual(ordered[1], self.asset2.id)

    def test_find_in_item_after_none_returns_first_not_started(self):
        item_id = self.asset1.item.item_id
        chosen = tc_find_in_item(self.campaign, item_id=item_id, after_asset_pk=None)
        self.assertEqual(chosen, self.asset1)

    def test_find_in_item_skips_inprog_and_reserved_and_advances(self):
        create_transcription(asset=self.asset1, user=self.anon)
        asset3 = create_asset(item=self.asset1.item, sequence=3, slug="tc-more-a3")
        AssetTranscriptionReservation.objects.create(
            asset=asset3, reservation_token="tc-res-a3"  # nosec
        )
        chosen = tc_find_in_item(
            self.campaign,
            item_id=self.asset1.item.item_id,
            after_asset_pk=self.asset1.id,
        )
        self.assertEqual(chosen, self.asset2)

    def test_find_in_item_after_missing_excludes_id_only(self):
        missing_pk = 987654321
        chosen = tc_find_in_item(
            self.campaign, item_id=self.asset1.item.item_id, after_asset_pk=missing_pk
        )
        self.assertEqual(chosen, self.asset1)

    def test_find_ns_in_proj_excludes_item_and_reserved(self):
        project = self.asset1.item.project
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())
        item2 = create_item(project=project, item_id="tc-more-it-2")
        not_started1 = create_asset(item=item2, sequence=1, slug="tc-more-ns1")
        not_started2 = create_asset(item=item2, sequence=2, slug="tc-more-ns2")
        AssetTranscriptionReservation.objects.create(
            asset=not_started1, reservation_token="tc-res-ns1"  # nosec
        )
        chosen = tc_find_ns_in_proj(
            self.campaign,
            project_slug=project.slug,
            exclude_item_id=self.asset1.item.item_id,
        )
        self.assertEqual(chosen, not_started2)

    def test_find_ns_in_proj_blank_slug_none(self):
        self.assertIsNone(tc_find_ns_in_proj(self.campaign, project_slug=""))

    @patch("concordia.utils.next_asset.transcribable.campaign.get_registered_task")
    def test_cache_same_item_is_ignored_then_manual_selects(self, mock_get_task):
        """
        Same-item cache entries should be ignored; manual should return other item.
        """
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())

        NextTranscribableCampaignAsset.objects.create(
            asset=self.asset2,
            campaign=self.campaign,
            item=self.asset2.item,
            item_item_id=self.asset2.item.item_id,
            project=self.asset2.item.project,
            project_slug=self.asset2.item.project.slug,
            sequence=self.asset2.sequence,
            transcription_status=TranscriptionStatus.NOT_STARTED,
        )

        item2 = create_item(project=self.asset1.item.project, item_id="tc-more-it-man")
        picked_asset = create_asset(item=item2, sequence=10, slug="tc-more-pick")

        chosen = find_next_transcribable_campaign_asset(
            self.campaign,
            project_slug="",  # skip project-level short-circuit
            item_id=self.asset1.item.item_id,  # forces same-item short-circuit first
            original_asset_id=self.asset1.id,
        )
        self.assertEqual(chosen, picked_asset)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    @patch("concordia.utils.next_asset.transcribable.campaign.get_registered_task")
    def test_manual_excludes_original_pk_and_same_item(self, mock_get_task):
        """
        Manual ranking must exclude the original asset and the current item.
        """
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        create_transcription(asset=self.asset2, user=self.anon, submitted=now())

        item2 = create_item(project=self.asset1.item.project, item_id="tc-more-it-3")
        keep = create_asset(item=item2, sequence=1, slug="tc-more-keep")
        toss = create_asset(item=item2, sequence=2, slug="tc-more-toss")

        chosen = find_next_transcribable_campaign_asset(
            self.campaign,
            project_slug="",
            item_id=self.asset1.item.item_id,
            original_asset_id=toss.id,
        )
        self.assertEqual(chosen, keep)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    def test_same_item_inprog_after_when_no_not_started(self):
        """
        If no NOT_STARTED anywhere qualifies, select IN_PROGRESS in same item.
        """
        create_transcription(asset=self.asset2, user=self.anon)  # IN_PROGRESS
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())

        got = find_next_transcribable_campaign_asset(
            self.campaign,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=self.asset1.id,
        )
        self.assertEqual(got, self.asset2)

    def test_eligible_base_qs_filters_status_and_published(self):
        create_transcription(asset=self.asset1, user=self.anon, submitted=now())
        not_started_asset = create_asset(
            item=self.asset1.item, sequence=3, slug="tc-more-ns-ok"
        )
        in_progress_asset = create_asset(
            item=self.asset1.item, sequence=4, slug="tc-more-ip-ok"
        )
        create_transcription(asset=in_progress_asset, user=self.anon)  # IN_PROGRESS

        other_campaign = create_campaign(slug="tc-ebq-c", title="tc-ebq-c")
        other_project = create_project(
            campaign=other_campaign, slug="tc-ebq-p", title="tc-ebq-p"
        )
        other_item = create_item(project=other_project, item_id="tc-ebq-i")
        other_asset = create_asset(item=other_item, slug="tc-ebq-a")

        queryset = tc_eligible_base_qs(self.campaign)
        id_set = set(queryset.values_list("id", flat=True))
        self.assertIn(not_started_asset.id, id_set)
        self.assertIn(in_progress_asset.id, id_set)
        self.assertNotIn(self.asset1.id, id_set)
        self.assertNotIn(other_asset.id, id_set)

    def test_cached_transcribable_accessor_returns_rows(self):
        row = NextTranscribableCampaignAsset.objects.create(
            asset=self.asset1,
            campaign=self.campaign,
            item=self.asset1.item,
            item_item_id=self.asset1.item.item_id,
            project=self.asset1.item.project,
            project_slug=self.asset1.item.project.slug,
            sequence=self.asset1.sequence,
            transcription_status=TranscriptionStatus.NOT_STARTED,
        )
        queryset = find_cached_transcribable_assets(self.campaign)
        self.assertIn(row.id, queryset.values_list("id", flat=True))

    def test_find_in_item_blank_item_id_none(self):
        chosen = tc_find_in_item(self.campaign, item_id="", after_asset_pk=None)
        self.assertIsNone(chosen)

    def test_find_ns_in_proj_without_exclude_includes_same_item(self):
        """
        exclude_item_id is falsy, so branch where no exclusion is applied.
        Should pick the first NOT_STARTED asset, even if it's in the same item.
        """
        project = self.asset1.item.project
        chosen = tc_find_ns_in_proj(self.campaign, project_slug=project.slug)
        self.assertEqual(chosen, self.asset1)
