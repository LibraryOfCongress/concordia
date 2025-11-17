import datetime
from time import time

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase, override_settings
from django.utils.timezone import make_aware, now

from concordia.models import (
    Asset,
    Transcription,
    TranscriptionStatus,
)
from concordia.views.utils import (
    AnonymousUserValidationCheckMixin,
    _get_pages,
    annotate_children_with_progress_stats,
    calculate_asset_stats,
)

from .utils import (
    CreateTestUsers,
    create_asset,
    create_campaign,
    create_item,
    create_project,
    create_transcription,
)


class GetPagesTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = self.create_test_user()

        # Base campaign, project, item setup
        self.campaign = create_campaign(slug="gp-camp", title="gp-camp")
        self.project = create_project(
            campaign=self.campaign, slug="gp-proj", title="gp-proj"
        )
        self.item = create_item(project=self.project, item_id="gp-item")

        # Two assets in the same item
        self.asset1 = create_asset(item=self.item, slug="gp-a1", sequence=1)
        self.asset2 = create_asset(item=self.item, slug="gp-a2", sequence=2)

        # Another campaign and project for campaign filtering tests
        self.campaign2 = create_campaign(slug="gp-camp-2", title="gp-camp-2")
        self.project2 = create_project(
            campaign=self.campaign2, slug="gp-proj-2", title="gp-proj-2"
        )
        self.item2 = create_item(project=self.project2, item_id="gp-item-2")
        self.asset3_other_campaign = create_asset(
            item=self.item2, slug="gp-a3", sequence=1
        )

    def _request(self, params: dict[str, str]):
        request = self.factory.get("/dummy", data=params)
        request.user = self.user
        return request

    def _touch_transcription_times(
        self,
        transcription: Transcription,
        *,
        created_on=None,
        updated_on=None,
        reviewer=None,
    ):
        if reviewer is not None:
            transcription.reviewed_by = reviewer
        if created_on is not None:
            transcription.created_on = created_on
        if updated_on is not None:
            transcription.updated_on = updated_on
        transcription.save(update_fields=["reviewed_by", "created_on", "updated_on"])

    def test_activity_filters_transcribed_vs_reviewed_vs_default(self):
        now_reference = now()

        # asset1: transcribed by self.user
        transcription1 = create_transcription(asset=self.asset1, user=self.user)
        self._touch_transcription_times(
            transcription1, created_on=now_reference - datetime.timedelta(hours=2)
        )

        # asset2: reviewed by self.user
        transcription2 = create_transcription(
            asset=self.asset2, user=self.create_test_user("transcriber")
        )
        self._touch_transcription_times(
            transcription2,
            reviewer=self.user,
            updated_on=now_reference - datetime.timedelta(hours=1),
        )

        # Default behavior includes both
        queryset_default = _get_pages(self._request({}))
        self.assertCountEqual(
            list(queryset_default.values_list("id", flat=True)),
            [self.asset1.id, self.asset2.id],
        )

        # Transcribed only
        queryset_transcribed = _get_pages(self._request({"activity": "transcribed"}))
        self.assertListEqual(
            list(queryset_transcribed.values_list("id", flat=True)),
            [self.asset1.id],
        )

        # Reviewed only
        queryset_reviewed = _get_pages(self._request({"activity": "reviewed"}))
        self.assertListEqual(
            list(queryset_reviewed.values_list("id", flat=True)),
            [self.asset2.id],
        )

    def test_status_filter_exclusions(self):
        # Ensure the user is associated with each asset via transcriptions
        create_transcription(asset=self.asset1, user=self.user)
        create_transcription(asset=self.asset2, user=self.user, submitted=now())

        # Mark asset1 as IN_PROGRESS explicitly
        Asset.objects.filter(pk=self.asset1.pk).update(
            transcription_status=TranscriptionStatus.IN_PROGRESS
        )

        # Also add an asset in COMPLETED with a user transcription
        completed_asset = create_asset(item=self.item, slug="gp-a4", sequence=3)
        create_transcription(asset=completed_asset, user=self.user)
        Asset.objects.filter(pk=completed_asset.pk).update(
            transcription_status=TranscriptionStatus.COMPLETED
        )

        # Only "submitted" requested, so exclude IN_PROGRESS and COMPLETED
        queryset = _get_pages(self._request({"status": "submitted"}))
        self.assertListEqual(
            list(queryset.values_list("id", flat=True)), [self.asset2.id]
        )

    def test_date_range_and_single_day_filters_and_ordering(self):
        # Transcriptions (associate user) with distinct activity dates
        today = now()
        day_minus_3 = make_aware(
            datetime.datetime.combine(
                (today - datetime.timedelta(days=3)).date(), datetime.time(12)
            )
        )
        day_minus_1 = make_aware(
            datetime.datetime.combine(
                (today - datetime.timedelta(days=1)).date(), datetime.time(12)
            )
        )

        transcription1 = create_transcription(asset=self.asset1, user=self.user)
        self._touch_transcription_times(
            transcription1, created_on=day_minus_3, updated_on=day_minus_3
        )

        transcription2 = create_transcription(asset=self.asset2, user=self.user)
        self._touch_transcription_times(
            transcription2, created_on=day_minus_1, updated_on=day_minus_1
        )

        # The range filter from two days ago through today should include
        # asset2 (day minus one) and exclude asset1 (day minus three)
        start = (today - datetime.timedelta(days=2)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")
        queryset_range = _get_pages(self._request({"start": start, "end": end}))
        self.assertListEqual(
            list(queryset_range.values_list("id", flat=True)), [self.asset2.id]
        )

        # A single-day filter for day minus three picks asset1
        only_day = (today - datetime.timedelta(days=3)).strftime("%Y-%m-%d")
        queryset_single = _get_pages(self._request({"start": only_day}))
        self.assertListEqual(
            list(queryset_single.values_list("id", flat=True)), [self.asset1.id]
        )

        # Ordering: ascending vs default (descending)
        queryset_ascending = _get_pages(self._request({"order_by": "date-ascending"}))
        self.assertEqual(
            list(queryset_ascending.values_list("id", flat=True)),
            [self.asset1.id, self.asset2.id],
        )

        queryset_descending = _get_pages(self._request({}))
        self.assertEqual(
            list(queryset_descending.values_list("id", flat=True)),
            [self.asset2.id, self.asset1.id],
        )

    def test_campaign_filter_and_six_month_cutoff(self):
        # Link user to assets in both campaigns
        recent_timestamp = now() - datetime.timedelta(days=5)
        old_timestamp = now() - datetime.timedelta(days=6 * 30 + 10)

        # Asset in base campaign (recent)
        transcription1 = create_transcription(asset=self.asset1, user=self.user)
        self._touch_transcription_times(
            transcription1, created_on=recent_timestamp, updated_on=recent_timestamp
        )

        # Asset in other campaign (recent)
        transcription2 = create_transcription(
            asset=self.asset3_other_campaign, user=self.user
        )
        self._touch_transcription_times(
            transcription2, created_on=recent_timestamp, updated_on=recent_timestamp
        )

        # Very old activity on asset2 so it should be filtered out by the
        # six months cutoff
        transcription_old = create_transcription(asset=self.asset2, user=self.user)
        self._touch_transcription_times(
            transcription_old, created_on=old_timestamp, updated_on=old_timestamp
        )

        # Without a campaign filter, both recent assets are present
        # and the old one is excluded
        queryset = _get_pages(self._request({}))
        asset_ids = set(queryset.values_list("id", flat=True))
        self.assertSetEqual(asset_ids, {self.asset1.id, self.asset3_other_campaign.id})

        # The campaign filter picks only the other campaign's asset
        queryset_campaign2 = _get_pages(
            self._request({"campaign": str(self.campaign2.pk)})
        )
        self.assertListEqual(
            list(queryset_campaign2.values_list("id", flat=True)),
            [self.asset3_other_campaign.id],
        )

    def test_status_filter_includes_completed_when_requested(self):
        """
        When "completed" is requested, completed assets are kept while
        submitted and in progress assets are excluded.
        """
        # Prepare three assets that all have activity from this user.
        completed_asset = create_asset(
            item=self.item, slug="gp-a4-completed", sequence=4
        )
        create_transcription(asset=completed_asset, user=self.user)
        Asset.objects.filter(pk=completed_asset.pk).update(
            transcription_status=TranscriptionStatus.COMPLETED
        )

        create_transcription(asset=self.asset1, user=self.user)
        Asset.objects.filter(pk=self.asset1.pk).update(
            transcription_status=TranscriptionStatus.IN_PROGRESS
        )

        create_transcription(
            asset=self.asset2, user=self.user, submitted=now()
        )  # submitted

        # Request only "completed" status.
        queryset = _get_pages(self._request({"status": "completed"}))
        self.assertListEqual(
            list(queryset.values_list("id", flat=True)), [completed_asset.id]
        )

    def test_status_filter_includes_in_progress_and_excludes_submitted_not_requested(
        self,
    ):
        """
        When "in_progress" is requested, in progress assets are kept and
        submitted assets are excluded because "submitted" is not requested.
        """
        # Prepare one in progress and one submitted asset with this user's activity.
        create_transcription(asset=self.asset1, user=self.user)
        Asset.objects.filter(pk=self.asset1.pk).update(
            transcription_status=TranscriptionStatus.IN_PROGRESS
        )

        create_transcription(
            asset=self.asset2, user=self.user, submitted=now()
        )  # submitted

        # Request only "in_progress" status.
        queryset = _get_pages(self._request({"status": "in_progress"}))
        ids = list(queryset.values_list("id", flat=True))
        self.assertIn(self.asset1.id, ids)
        self.assertNotIn(self.asset2.id, ids)


class CalculateAssetStatsTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.user = self.create_test_user()
        self.campaign = create_campaign(slug="cas-c", title="cas-c")
        self.project = create_project(
            campaign=self.campaign, slug="cas-p", title="cas-p"
        )
        self.item = create_item(project=self.project, item_id="cas-i")

    def test_counts_percents_and_contributors_remove_none_branch(self):
        # Build a small asset set with varied statuses.
        asset_not_started = create_asset(item=self.item, slug="cas-ns", sequence=1)
        asset_in_progress = create_asset(item=self.item, slug="cas-ip", sequence=2)
        asset_submitted = create_asset(item=self.item, slug="cas-sub", sequence=3)

        # Set desired statuses directly.
        Asset.objects.filter(pk=asset_not_started.pk).update(
            transcription_status=TranscriptionStatus.NOT_STARTED
        )
        Asset.objects.filter(pk=asset_in_progress.pk).update(
            transcription_status=TranscriptionStatus.IN_PROGRESS
        )
        Asset.objects.filter(pk=asset_submitted.pk).update(
            transcription_status=TranscriptionStatus.SUBMITTED
        )

        # Create transcriptions ONLY for the assets that should not remain NOT_STARTED.
        # For IN_PROGRESS, a plain transcription moves or keeps the asset in progress.
        transcription_in_progress = create_transcription(
            asset=asset_in_progress, user=self.user
        )
        # For SUBMITTED, mark the transcription as submitted so the
        # signal preserves SUBMITTED.
        transcription_submitted = create_transcription(
            asset=asset_submitted, user=self.user, submitted=now()
        )
        # Ensure there is at least one None in reviewed_by so the remove(None)
        # path is exercised.
        Transcription.objects.filter(
            pk__in=[transcription_in_progress.pk, transcription_submitted.pk]
        ).update(reviewed_by=None)

        context = {}
        calculate_asset_stats(
            Asset.objects.filter(
                pk__in=[asset_not_started.pk, asset_in_progress.pk, asset_submitted.pk]
            ),
            context,
        )

        # contributor_count counts unique user_ids and reviewed_by values, minus None.
        self.assertEqual(context["contributor_count"], 1)

        # Counts per status.
        self.assertEqual(context["not_started_count"], 1)
        self.assertEqual(context["in_progress_count"], 1)
        self.assertEqual(context["submitted_count"], 1)
        # COMPLETED not present.
        self.assertEqual(context.get("completed_count", 0), 0)

        # Percentages should round sensibly for 1 out of 3.
        self.assertEqual(context["not_started_percent"], round(100 * (1 / 3)))
        self.assertEqual(context["in_progress_percent"], round(100 * (1 / 3)))
        self.assertEqual(context["submitted_percent"], round(100 * (1 / 3)))

        # Labeled list populated and includes "not_started".
        self.assertTrue(
            any(
                status_key == "not_started"
                for status_key, _, _ in context["transcription_status_counts"]
            )
        )

    def test_contributors_keyerror_branch_and_cap_99(self):
        # Create 100 assets and set 99 to NOT_STARTED and 1 to IN_PROGRESS.
        assets = []
        for i in range(1, 101):
            a = create_asset(item=self.item, slug=f"cas-bulk-{i}", sequence=i)
            assets.append(a)

        Asset.objects.filter(pk__in=[a.pk for a in assets[:99]]).update(
            transcription_status=TranscriptionStatus.NOT_STARTED
        )
        Asset.objects.filter(pk=assets[-1].pk).update(
            transcription_status=TranscriptionStatus.IN_PROGRESS
        )

        # Create a transcription ONLY for the single IN_PROGRESS asset
        # and set a reviewer. This ensures there is no None in reviewed_by,
        # which triggers the KeyError branch when calculate_asset_stats
        # attempts to remove(None) from the contributor set.
        other_user = self.create_test_user(username="cas-reviewer")
        transcription = create_transcription(asset=assets[-1], user=self.user)
        transcription.reviewed_by = other_user
        transcription.save(update_fields=["reviewed_by"])

        context = {}
        calculate_asset_stats(
            Asset.objects.filter(pk__in=[a.pk for a in assets]), context
        )

        # Two distinct contributors: the creator (self.user) and
        # the reviewer (other_user).
        self.assertEqual(context["contributor_count"], 2)

        # Verify percentages and that the 99 percent capping behavior is applied.
        self.assertEqual(context["not_started_percent"], 99)
        self.assertEqual(context["in_progress_percent"], 1)
        self.assertEqual(context.get("submitted_percent", 0), 0)
        self.assertEqual(context.get("completed_percent", 0), 0)

        # Also verify counts to ensure the underlying distribution is as intended.
        self.assertEqual(context["not_started_count"], 99)
        self.assertEqual(context["in_progress_count"], 1)
        self.assertEqual(context.get("submitted_count", 0), 0)
        self.assertEqual(context.get("completed_count", 0), 0)


class AnnotateChildrenProgressStatsTests(TestCase):
    class Obj:
        pass

    def test_progress_stats_with_capping_and_lowest_status(self):
        obj = self.Obj()
        # Construct counts such that one bucket yields at least ninety nine
        # but less than one hundred percent
        obj.not_started_count = 99
        obj.in_progress_count = 1
        obj.submitted_count = 0
        obj.completed_count = 0

        annotate_children_with_progress_stats([obj])

        # Total
        self.assertEqual(obj.total_count, 100)
        # Capping at ninety nine
        self.assertEqual(obj.not_started_percent, 99)
        # Others
        self.assertEqual(obj.in_progress_percent, 1)
        self.assertEqual(obj.submitted_percent, 0)
        self.assertEqual(obj.completed_percent, 0)
        # Lowest is the first non-zero by CHOICES order; expect "not_started"
        self.assertEqual(obj.lowest_transcription_status, "not_started")

    def test_progress_stats_zero_total(self):
        obj = self.Obj()
        obj.not_started_count = 0
        obj.in_progress_count = 0
        obj.submitted_count = 0
        obj.completed_count = 0

        annotate_children_with_progress_stats([obj])

        self.assertEqual(obj.total_count, 0)
        self.assertEqual(obj.not_started_percent, 0)
        self.assertEqual(obj.in_progress_percent, 0)
        self.assertEqual(obj.submitted_percent, 0)
        self.assertEqual(obj.completed_percent, 0)
        self.assertIsNone(obj.lowest_transcription_status)


class _BaseView:
    """
    Minimal base class that provides get_context_data so the mixin can call super().
    """

    def get_context_data(self, **kwargs):
        return {}


class DummyTemplateView(AnonymousUserValidationCheckMixin, _BaseView):
    """
    Stand-in view. The mixin is first in the MRO so its get_context_data runs,
    then it calls super() which resolves to _BaseView.get_context_data.
    """

    pass


class AnonymousUserValidationCheckMixinTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = self.create_test_user()

    def _attach_session(self, request):
        # Attach a session dictionary-like attribute without middleware dependency
        request.session = {}
        return request

    @override_settings(ANONYMOUS_USER_VALIDATION_INTERVAL=10)
    def test_unauthenticated_requires_validation_when_stale(self):
        request = self.factory.get("/dummy")
        request.user = AnonymousUser()
        self._attach_session(request)
        # There is no prior validation so the default timestamp is zero
        # and the validation is stale
        view = DummyTemplateView()
        view.request = request
        context = view.get_context_data()
        self.assertTrue(context["anonymous_user_validation_required"])

    @override_settings(ANONYMOUS_USER_VALIDATION_INTERVAL=10)
    def test_unauthenticated_recent_validation_is_not_required(self):
        request = self.factory.get("/dummy")
        request.user = AnonymousUser()
        self._attach_session(request)
        request.session["turnstile_last_validated"] = int(time())
        view = DummyTemplateView()
        view.request = request
        context = view.get_context_data()
        self.assertFalse(context["anonymous_user_validation_required"])

    @override_settings(ANONYMOUS_USER_VALIDATION_INTERVAL=10)
    def test_authenticated_never_requires_validation(self):
        request = self.factory.get("/dummy")
        request.user = self.user
        self._attach_session(request)
        view = DummyTemplateView()
        view.request = request
        context = view.get_context_data()
        self.assertFalse(context["anonymous_user_validation_required"])
