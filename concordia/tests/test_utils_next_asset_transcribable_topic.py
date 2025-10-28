from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils.timezone import now

from concordia.models import (
    Asset,
    AssetTranscriptionReservation,
    NextTranscribableTopicAsset,
    TranscriptionStatus,
)
from concordia.utils import get_anonymous_user
from concordia.utils.next_asset import (
    find_new_transcribable_topic_assets,
    find_next_transcribable_topic_asset,
    find_transcribable_topic_asset,
)
from concordia.utils.next_asset.transcribable.topic import (
    _eligible_transcribable_base_qs as topic_transcribable_eligible_base_qs,
)
from concordia.utils.next_asset.transcribable.topic import (
    _find_transcribable_in_item_for_topic as topic_find_in_item_for_topic,
)
from concordia.utils.next_asset.transcribable.topic import (
    _find_transcribable_not_started_in_project_for_topic,
    find_and_order_potential_transcribable_topic_assets,
    find_invalid_next_transcribable_topic_assets,
)
from concordia.utils.next_asset.transcribable.topic import (
    _next_seq_after as topic_next_seq_after_for_transcribable,
)
from concordia.utils.next_asset.transcribable.topic import (
    _order_unstarted_first as topic_order_unstarted_first,
)
from concordia.utils.next_asset.transcribable.topic import (
    _reserved_asset_ids_subq as topic_transcribable_reserved_ids_subq,
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

topic_find_not_started_in_project_for_topic = (
    _find_transcribable_not_started_in_project_for_topic
)
find_invalid_next_transcribable_topic_assets_fn = (
    find_invalid_next_transcribable_topic_assets
)


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
        assert_in = self.assertIn
        assert_in(self.asset2, queryset)

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


class TranscribableTopicInternalsTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.anonymous = get_anonymous_user()
        self.user = self.create_test_user()
        self.asset1 = create_asset(sequence=1, slug="tt-int-a1")
        self.asset2 = create_asset(item=self.asset1.item, sequence=2, slug="tt-int-a2")
        self.topic = create_topic(project=self.asset1.item.project)

    def test_topic_transcribable_reserved_ids_is_unfiltered(self):
        AssetTranscriptionReservation.objects.create(
            asset=self.asset1, reservation_token="tt-res-here"  # nosec
        )
        other_campaign = create_campaign(slug="tt-oc", title="tt-oc")
        other_project = create_project(
            campaign=other_campaign, slug="tt-op", title="tt-op"
        )
        other_item = create_item(project=other_project, item_id="tt-oi")
        other_asset = create_asset(item=other_item, slug="tt-oa")
        AssetTranscriptionReservation.objects.create(
            asset=other_asset, reservation_token="tt-res-there"  # nosec
        )
        ids = set(
            topic_transcribable_reserved_ids_subq().values_list("asset_id", flat=True)
        )
        self.assertIn(self.asset1.id, ids)
        self.assertIn(other_asset.id, ids)

    def test_topic_transcribable_eligible_base_qs_filters_correctly(self):
        # Submitted, so excluded
        create_transcription(asset=self.asset2, user=self.anonymous, submitted=now())
        # Not started (included)
        asset_not_started = self.asset1
        # In progress (included)
        asset_in_progress = create_asset(
            item=self.asset1.item, sequence=3, slug="tt-int-ip"
        )
        create_transcription(asset=asset_in_progress, user=self.anonymous)
        # Other campaign (excluded)
        other_campaign = create_campaign(slug="tt-ebq-c", title="tt-ebq-c")
        other_project = create_project(
            campaign=other_campaign, slug="tt-ebq-p", title="tt-ebq-p"
        )
        other_item = create_item(project=other_project, item_id="tt-ebq-i")
        other_asset = create_asset(item=other_item, slug="tt-ebq-a")
        queryset = topic_transcribable_eligible_base_qs(self.topic)
        ids = set(queryset.values_list("id", flat=True))
        self.assertIn(asset_not_started.id, ids)
        self.assertIn(asset_in_progress.id, ids)
        self.assertNotIn(self.asset2.id, ids)
        self.assertNotIn(other_asset.id, ids)

    def test_topic_next_seq_after_variants_for_transcribable(self):
        self.assertIsNone(topic_next_seq_after_for_transcribable(None))
        self.assertIsNone(topic_next_seq_after_for_transcribable(987654321))
        self.assertEqual(
            topic_next_seq_after_for_transcribable(self.asset2.id),
            self.asset2.sequence,
        )

    def test_topic_find_in_item_for_topic_after_none_returns_first_not_started(self):
        chosen = topic_find_in_item_for_topic(
            self.topic, item_id=self.asset1.item.item_id, after_asset_pk=None
        )
        self.assertEqual(chosen, self.asset1)

    def test_topic_find_in_item_for_topic_skips_reserved_and_advances(self):
        third = create_asset(item=self.asset1.item, sequence=3, slug="tt-int-a3")
        AssetTranscriptionReservation.objects.create(
            asset=self.asset2, reservation_token="tt-int-a2"  # nosec
        )
        chosen = topic_find_in_item_for_topic(
            self.topic,
            item_id=self.asset1.item.item_id,
            after_asset_pk=self.asset1.id,
        )
        self.assertEqual(chosen, third)

    def test_topic_find_in_item_for_topic_after_missing_excludes_only_id(self):
        chosen = topic_find_in_item_for_topic(
            self.topic,
            item_id=self.asset1.item.item_id,
            after_asset_pk=987654321,
        )
        self.assertEqual(chosen, self.asset1)

    def test_topic_find_in_item_for_topic_blank_item_id_returns_none(self):
        chosen = topic_find_in_item_for_topic(
            self.topic, item_id="", after_asset_pk=None
        )
        self.assertIsNone(chosen)

    def test_topic_find_not_started_in_project_excludes_item_and_reserved(self):
        other_item = create_item(project=self.asset1.item.project, item_id="tt-int-ex")
        not_started_1 = create_asset(item=other_item, sequence=1, slug="tt-int-ns1")
        not_started_2 = create_asset(item=other_item, sequence=2, slug="tt-int-ns2")
        AssetTranscriptionReservation.objects.create(
            asset=not_started_1, reservation_token="tt-int-res"  # nosec
        )
        chosen = topic_find_not_started_in_project_for_topic(
            self.topic,
            project_slug=self.asset1.item.project.slug,
            exclude_item_id=self.asset1.item.item_id,
        )
        self.assertEqual(chosen, not_started_2)

    def test_topic_find_not_started_in_project_blank_slug_none(self):
        self.assertIsNone(
            topic_find_not_started_in_project_for_topic(self.topic, project_slug="")
        )

    def test_topic_order_unstarted_first_prefers_not_started(self):
        in_progress = create_asset(
            item=self.asset1.item, sequence=4, slug="tt-int-ip-2"
        )
        create_transcription(asset=in_progress, user=self.anonymous)
        queryset = Asset.objects.filter(id__in=[self.asset1.id, in_progress.id])
        ordered = list(
            topic_order_unstarted_first(queryset).values_list("id", flat=True)
        )
        self.assertEqual(ordered[0], self.asset1.id)
        self.assertEqual(ordered[1], in_progress.id)

    def test_topic_find_not_started_in_project_without_exclude_includes_same_item(
        self,
    ):
        """
        With exclude_item_id falsy, the helper should consider the same item and
        pick the first NOT_STARTED asset there (covers the else branch of L154->157).
        """
        project = self.asset1.item.project
        chosen = topic_find_not_started_in_project_for_topic(
            self.topic, project_slug=project.slug, exclude_item_id=""
        )
        self.assertEqual(chosen, self.asset1)


class NextTranscribableTopicMoreTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.anonymous = get_anonymous_user()
        self.user = self.create_test_user()
        self.asset1 = create_asset(slug="tt-more-a1", sequence=1, title="TT More A1")
        self.asset2 = create_asset(
            item=self.asset1.item, slug="tt-more-a2", sequence=2, title="TT More A2"
        )
        self.topic = create_topic(project=self.asset1.item.project)

    def test_new_transcribable_topic_excludes_reserved_and_cached(self):
        reserved_asset = create_asset(
            item=self.asset1.item, sequence=3, slug="tt-more-res"
        )
        cached_asset = create_asset(
            item=self.asset1.item, sequence=4, slug="tt-more-cached"
        )
        NextTranscribableTopicAsset.objects.create(
            asset=cached_asset,
            topic=self.topic,
            item=cached_asset.item,
            item_item_id=cached_asset.item.item_id,
            project=cached_asset.item.project,
            project_slug=cached_asset.item.project.slug,
            sequence=cached_asset.sequence,
            transcription_status=TranscriptionStatus.NOT_STARTED,
        )
        AssetTranscriptionReservation.objects.create(
            asset=reserved_asset, reservation_token="tt-more-rv"  # nosec
        )
        queryset = find_new_transcribable_topic_assets(self.topic)
        self.assertNotIn(reserved_asset, queryset)
        self.assertNotIn(cached_asset, queryset)

    def test_find_and_order_potential_transcribable_topic_assets_ordering(self):
        base_item = self.asset1.item
        same_item_next = create_asset(
            item=base_item, sequence=10, slug="tt-pot-ci-next"
        )
        same_project_other_item = create_asset(
            item=create_item(project=base_item.project, item_id="tt-pot-it-2"),
            sequence=5,
            slug="tt-pot-proj",
        )
        other_project = create_project(
            campaign=self.asset1.campaign,
            slug="tt-pot-proj-oth",
            title="tt-pot-proj-oth",
        )
        other_item = create_item(project=other_project, item_id="tt-pot-it-3")
        other_project_asset = create_asset(
            item=other_item, sequence=1, slug="tt-pot-op"
        )

        for asset in (same_item_next, same_project_other_item, other_project_asset):
            NextTranscribableTopicAsset.objects.create(
                asset=asset,
                topic=self.topic,
                item=asset.item,
                item_item_id=asset.item.item_id,
                project=asset.item.project,
                project_slug=asset.item.project.slug,
                sequence=asset.sequence,
                transcription_status=TranscriptionStatus.NOT_STARTED,
            )

        ordered = find_and_order_potential_transcribable_topic_assets(
            self.topic,
            project_slug=base_item.project.slug,
            item_id=base_item.item_id,
            asset_pk=self.asset1.id,
        ).values_list("asset_id", flat=True)

        ordered = list(ordered)
        # Prefer same item, then same project, then others
        self.assertEqual(ordered[0], same_item_next.id)
        self.assertEqual(ordered[1], same_project_other_item.id)
        self.assertIn(other_project_asset.id, ordered[2:])

    def test_find_invalid_next_transcribable_topic_assets_reserved_and_status(self):
        reserved_asset = create_asset(
            item=self.asset1.item, sequence=30, slug="tt-inv-res"
        )
        create_transcription(asset=reserved_asset, user=self.anonymous)
        AssetTranscriptionReservation.objects.create(
            asset=reserved_asset, reservation_token="tt-inv-rv"  # nosec
        )
        NextTranscribableTopicAsset.objects.create(
            asset=reserved_asset,
            topic=self.topic,
            item=reserved_asset.item,
            item_item_id=reserved_asset.item.item_id,
            project=reserved_asset.item.project,
            project_slug=reserved_asset.item.project.slug,
            sequence=reserved_asset.sequence,
            transcription_status=TranscriptionStatus.IN_PROGRESS,
        )
        wrong_status_asset = create_asset(
            item=self.asset1.item, sequence=31, slug="tt-inv-wrong"
        )
        create_transcription(
            asset=wrong_status_asset, user=self.anonymous, submitted=now()
        )
        NextTranscribableTopicAsset.objects.create(
            asset=wrong_status_asset,
            topic=self.topic,
            item=wrong_status_asset.item,
            item_item_id=wrong_status_asset.item.item_id,
            project=wrong_status_asset.item.project,
            project_slug=wrong_status_asset.item.project.slug,
            sequence=wrong_status_asset.sequence,
            transcription_status=TranscriptionStatus.NOT_STARTED,
        )
        bad = list(
            find_invalid_next_transcribable_topic_assets_fn(self.topic.id).values_list(
                "asset_id", flat=True
            )
        )
        self.assertIn(reserved_asset.id, bad)
        self.assertIn(wrong_status_asset.id, bad)

    @patch("concordia.utils.next_asset.transcribable.topic.get_registered_task")
    def test_cache_same_item_is_ignored_then_manual_selects_topic(self, mock_get_task):
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        # Same-item cached row should be excluded, forcing manual fallback.
        NextTranscribableTopicAsset.objects.create(
            asset=self.asset2,
            topic=self.topic,
            item=self.asset2.item,
            item_item_id=self.asset2.item.item_id,
            project=self.asset2.item.project,
            project_slug=self.asset2.item.project.slug,
            sequence=self.asset2.sequence,
            transcription_status=TranscriptionStatus.NOT_STARTED,
        )
        # Make same-item short-circuit fail by reserving the only candidate.
        AssetTranscriptionReservation.objects.create(
            asset=self.asset2, reservation_token="tt-cache-same"  # nosec
        )
        # Provide a valid choice elsewhere to be picked by manual fallback.
        other_item = create_item(
            project=self.asset1.item.project, item_id="tt-cache-oth"
        )
        picked = create_asset(item=other_item, sequence=5, slug="tt-cache-pick")

        chosen = find_next_transcribable_topic_asset(
            self.topic,
            project_slug="",
            item_id=self.asset1.item.item_id,
            original_asset_id=self.asset1.id,
        )
        self.assertEqual(chosen, picked)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    @patch("concordia.utils.next_asset.transcribable.topic.get_registered_task")
    def test_cache_excludes_original_pk_and_chooses_next_topic(self, mock_get_task):
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        other_item = create_item(
            project=self.asset1.item.project, item_id="tt-cache-exc"
        )
        first = create_asset(item=other_item, sequence=1, slug="tt-cache-first")
        second = create_asset(item=other_item, sequence=2, slug="tt-cache-second")
        for asset in (first, second):
            NextTranscribableTopicAsset.objects.create(
                asset=asset,
                topic=self.topic,
                item=asset.item,
                item_item_id=asset.item.item_id,
                project=asset.item.project,
                project_slug=asset.item.project.slug,
                sequence=asset.sequence,
                transcription_status=TranscriptionStatus.NOT_STARTED,
            )

        chosen = find_next_transcribable_topic_asset(
            self.topic, project_slug="", item_id="", original_asset_id=first.id
        )
        self.assertEqual(chosen, second)
        self.assertFalse(mock_get_task.called)
        self.assertFalse(mock_task.delay.called)

    def test_same_item_inprogress_selected_when_no_not_started_topic(self):
        create_transcription(asset=self.asset2, user=self.anonymous)
        create_transcription(asset=self.asset1, user=self.anonymous, submitted=now())
        got = find_next_transcribable_topic_asset(
            self.topic,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=None,
        )
        self.assertEqual(got, self.asset2)

    @patch("concordia.utils.next_asset.transcribable.topic.get_registered_task")
    def test_next_transcribable_topic_none_anywhere_returns_none_no_spawn(
        self, mock_get_task
    ):
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        # Use a brand-new topic with no eligible assets anywhere.
        empty_campaign = create_campaign(slug="tt-none-c", title="tt-none-c")
        empty_project = create_project(
            campaign=empty_campaign, slug="tt-none-p", title="tt-none-p"
        )
        empty_topic = create_topic(project=empty_project)

        chosen = find_next_transcribable_topic_asset(
            topic=empty_topic, project_slug="", item_id="", original_asset_id=None
        )
        self.assertIsNone(chosen)
        self.assertFalse(mock_get_task.called)
        self.assertFalse(mock_task.delay.called)

    def test_item_gate_ignored_when_original_is_other_item_topic(self):
        """
        original_asset_id exists but belongs to a different item; item gate is ignored
        and we return the first NOT_STARTED in the requested item
        """
        other_item = create_item(
            project=self.asset1.item.project, item_id="tt-oth-item"
        )
        other_asset = create_asset(item=other_item, slug="tt-oth-a")

        chosen = find_next_transcribable_topic_asset(
            self.topic,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=other_asset.id,
        )
        self.assertEqual(chosen, self.asset1)

    def test_item_digit_string_missing_treats_as_no_after_topic(self):
        chosen = find_next_transcribable_topic_asset(
            self.topic,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id="987654321",  # valid digits, missing PK
        )
        self.assertEqual(chosen, self.asset1)

    @patch("concordia.utils.next_asset.transcribable.topic.get_registered_task")
    def test_manual_same_item_ip_when_no_ns_anywhere_topic(self, mock_get_task):
        """
        Manual fallback path with item_id present: when there are
        no NOT_STARTED anywhere, choose same-item IN_PROGRESS.
        """
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        # No NOT_STARTED anywhere in this topic's project; only same-item IN_PROGRESS
        create_transcription(asset=self.asset2, user=self.anonymous)  # IN_PROGRESS
        create_transcription(asset=self.asset1, user=self.anonymous, submitted=now())

        got = find_next_transcribable_topic_asset(
            self.topic,
            project_slug="",  # bypass short-circuit so we hit the manual path
            item_id=self.asset1.item.item_id,
            original_asset_id=None,
        )
        self.assertEqual(got, self.asset2)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    def test_item_invalid_after_str_valueerror_branch_topic(self):
        chosen = find_next_transcribable_topic_asset(
            self.topic,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id="not-an-int",
        )
        self.assertEqual(chosen, self.asset1)

    @patch("concordia.utils.next_asset.transcribable.topic.get_registered_task")
    def test_manual_valid_after_excludes_original_and_picks_next_topic(
        self, mock_get_task
    ):
        """
        Manual fallback with a valid original_asset_id: use after_seq to exclude the
        original and return the next NOT_STARTED
        """
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        other_item = create_item(
            project=self.asset1.item.project, item_id="tt-man-item"
        )
        first = create_asset(item=other_item, sequence=1, slug="tt-man-first")
        second = create_asset(item=other_item, sequence=2, slug="tt-man-second")

        chosen = find_next_transcribable_topic_asset(
            self.topic,
            project_slug="",
            item_id="",
            original_asset_id=first.id,
        )
        self.assertEqual(chosen, second)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    @patch("concordia.utils.next_asset.transcribable.topic.get_registered_task")
    def test_inprogress_fallback_spawns_and_uses_after_gate_topic(self, mock_get_task):
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        # Make original (seq=1) SUBMITTED so it can't be chosen; keep it as "original".
        create_transcription(asset=self.asset1, user=self.anonymous, submitted=now())
        # Only candidate anywhere: same-item IN_PROGRESS (seq=2).
        create_transcription(asset=self.asset2, user=self.anonymous)  # IN_PROGRESS

        # Ensure there are no other items/assets in the topic to be found
        # by manual path (manual path excludes same item when item_id is provided).
        # No cached rows either.

        chosen = find_next_transcribable_topic_asset(
            self.topic,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=self.asset1.id,
        )

        self.assertEqual(chosen, self.asset2)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    @patch("concordia.utils.next_asset.transcribable.topic.get_registered_task")
    def test_inprogress_fallback_with_digit_string_original_id(self, mock_get_task):
        """
        Same as above, but pass original_asset_id as a DIGIT STRING to
        exercise the int(original_asset_id) path inside the after-seq filter.
        Also ensures exclude(pk=original_asset_id) runs without ValueError.
        """
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        # Original: SUBMITTED, seq=1
        create_transcription(asset=self.asset1, user=self.anonymous, submitted=now())
        # Only candidate: same-item IN_PROGRESS, seq=2
        create_transcription(asset=self.asset2, user=self.anonymous)

        chosen = find_next_transcribable_topic_asset(
            self.topic,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=str(self.asset1.id),
        )

        self.assertEqual(chosen, self.asset2)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    @patch("concordia.utils.next_asset.transcribable.topic.get_registered_task")
    def test_inprogress_fallback_spawns_and_returns_asset_topic(self, mock_get_task):
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        # Use a brand-new topic/project so no cached rows can interfere.
        campaign = create_campaign(slug="tt-ip-c1", title="tt-ip-c1")
        project = create_project(
            campaign=campaign,
            slug="tt-ip-p1",
            title="tt-ip-p1",
        )
        topic = create_topic(project=project)
        item = create_item(project=project, item_id="tt-ip-i1")

        asset1 = create_asset(item=item, sequence=1, slug="tt-ip-a1")
        asset2 = create_asset(item=item, sequence=2, slug="tt-ip-a2")
        create_transcription(asset=asset1, user=get_anonymous_user(), submitted=now())
        create_transcription(asset=asset2, user=get_anonymous_user())

        chosen = find_next_transcribable_topic_asset(
            topic=topic,
            project_slug=project.slug,
            item_id=item.item_id,
            original_asset_id=asset1.id,
        )

        self.assertEqual(chosen, asset2)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    @patch("concordia.utils.next_asset.transcribable.topic.get_registered_task")
    def test_inprogress_fallback_with_digit_str_original_id_topic(self, mock_get_task):
        """
        Same scenario as above, but pass original_asset_id as a DIGIT STRING to
        run the int(...) path inside the after-seq filter and still spawn the task.
        """
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        campaign = create_campaign(slug="tt-ip-c2", title="tt-ip-c2")
        project = create_project(
            campaign=campaign,
            slug="tt-ip-p2",
            title="tt-ip-p2",
        )
        topic = create_topic(project=project)
        item = create_item(project=project, item_id="tt-ip-i2")

        asset1 = create_asset(item=item, sequence=1, slug="tt-ip2-a1")
        asset2 = create_asset(item=item, sequence=2, slug="tt-ip2-a2")
        create_transcription(asset=asset1, user=get_anonymous_user(), submitted=now())
        create_transcription(asset=asset2, user=get_anonymous_user())  # IN_PROGRESS

        chosen = find_next_transcribable_topic_asset(
            topic=topic,
            project_slug=project.slug,
            item_id=item.item_id,
            original_asset_id=str(asset1.id),  # digit-string pk
        )

        self.assertEqual(chosen, asset2)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    def test_project_short_circuit_topic_excludes_current_item_via_item_filter(self):
        """
        project-level short-circuit executes with item_id truthy,
        so the code runs candidate = candidate.exclude(item__item_id=item_id).
        Item-level has no NOT_STARTED, so we land in the project block.
        """
        # Exhaust current item (no NOT_STARTED left there)
        create_transcription(asset=self.asset1, user=self.anonymous, submitted=now())
        create_transcription(asset=self.asset2, user=self.anonymous, submitted=now())

        # Create a NOT_STARTED candidate in the same project but a different item
        other_item = create_item(
            project=self.asset1.item.project, item_id="tt-proj-ex-branch"
        )
        pick = create_asset(item=other_item, sequence=1, slug="tt-proj-ex-pick")

        chosen = find_next_transcribable_topic_asset(
            self.topic,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=self.asset1.id,
        )
        self.assertEqual(chosen, pick)

    @patch("concordia.utils.next_asset.transcribable.topic.get_registered_task")
    def test_inprogress_fallback_spawns_task_with_item_id_topic(self, mock_get_task):
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        # Same item: one IN_PROGRESS, one SUBMITTED -> no NOT_STARTED anywhere.
        create_transcription(asset=self.asset2, user=self.anonymous)
        create_transcription(asset=self.asset1, user=self.anonymous, submitted=now())

        # With item_id set, manual fallback excludes same-item candidates, so
        # it returns nothing (spawn_task=True). Then the IN_PROGRESS fallback
        # must return asset2 and trigger the task.
        chosen = find_next_transcribable_topic_asset(
            self.topic,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=None,
        )
        self.assertEqual(chosen, self.asset2)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    @patch("concordia.utils.next_asset.transcribable.topic.get_registered_task")
    def test_manual_same_item_inprogress_triggers_spawn_task_topic(self, mock_get_task):
        """
        When there are no NOT_STARTED candidates anywhere (after excluding current
        item/original in the manual fallback), the same-item IN_PROGRESS fallback
        should return an asset AND spawn the cache population task.
        """
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        # Same item only:
        # - original (NOT_STARTED) will be excluded by manual fallback,
        # - next is IN_PROGRESS (eligible for final fallback).
        create_transcription(asset=self.asset2, user=self.anonymous)

        chosen = find_next_transcribable_topic_asset(
            self.topic,
            project_slug="",
            item_id=self.asset1.item.item_id,
            original_asset_id=self.asset1.id,
        )
        self.assertEqual(chosen, self.asset2)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)

    @patch("concordia.utils.next_asset.transcribable.topic.get_registered_task")
    def test_project_short_circuit_excludes_current_item_topic(self, mock_get_task):
        create_transcription(asset=self.asset1, user=self.anonymous, submitted=now())
        create_transcription(asset=self.asset2, user=self.anonymous, submitted=now())

        other_item = create_item(
            project=self.asset1.item.project, item_id="topic-proj-exclude-item"
        )
        pick = create_asset(item=other_item, sequence=5, slug="topic-proj-exclude-pick")

        chosen = find_next_transcribable_topic_asset(
            self.topic,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=self.asset1.id,
        )
        self.assertEqual(chosen, pick)
        self.assertFalse(mock_get_task.called)

    @patch("concordia.utils.next_asset.transcribable.topic.get_registered_task")
    def test_manual_inprogress_fallback_triggers_spawn_task_topic(self, mock_get_task):
        mock_task = mock_get_task.return_value
        mock_task.delay = MagicMock()

        create_transcription(asset=self.asset1, user=self.anonymous, submitted=now())
        create_transcription(asset=self.asset2, user=self.anonymous)

        chosen = find_next_transcribable_topic_asset(
            self.topic,
            project_slug=self.asset1.item.project.slug,
            item_id=self.asset1.item.item_id,
            original_asset_id=None,
        )
        self.assertEqual(chosen, self.asset2)
        self.assertTrue(mock_get_task.called)
        self.assertTrue(mock_task.delay.called)
