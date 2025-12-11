from unittest import mock

from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase

from concordia.models import Asset, Project
from concordia.tasks.retirement import (
    assets_removal_success,
    delete_asset,
    item_removal_success,
    project_removal_success,
    remove_next_assets,
    remove_next_item,
    remove_next_project,
    retire_campaign,
)

from .utils import (
    create_asset,
    create_campaign,
    create_campaign_retirement_progress,
    create_item,
    create_project,
)


class RetirementTasksTests(TestCase):
    def test_retire_campaign_initializes_totals_and_sets_status_and_triggers(self):
        # Build a campaign with 2 projects, 2 items, 3 assets.
        camp = create_campaign(slug="ret-c1")
        p1 = create_project(campaign=camp, slug="ret-p1")
        p2 = create_project(campaign=camp, slug="ret-p2")
        i1 = create_item(project=p1, item_id="ret-i1")
        i2 = create_item(project=p2, item_id="ret-i2")
        a1 = create_asset(item=i1, slug="ret-a1")
        a2 = create_asset(item=i1, slug="ret-a2")
        a3 = create_asset(item=i2, slug="ret-a3")
        self.assertTrue(all([a1.pk, a2.pk, a3.pk]))

        with mock.patch(
            "concordia.tasks.retirement.remove_next_project.delay"
        ) as m_delay:
            prog = retire_campaign(camp.id)

        prog.refresh_from_db()
        self.assertEqual(prog.project_total, 2)
        self.assertEqual(prog.item_total, 2)
        self.assertEqual(prog.asset_total, 3)
        camp.refresh_from_db()
        # Status must be set to RETIRED.
        self.assertEqual(camp.status, camp.Status.RETIRED)  # type: ignore[attr-defined]
        m_delay.assert_called_once_with(camp.id)

    def test_retire_campaign_existing_progress_and_already_retired(self):
        camp = create_campaign(slug="ret-c2")
        # Pre-create progress so the totals branch is skipped.
        prog = create_campaign_retirement_progress(campaign=camp)
        prog.project_total = 7
        prog.item_total = 8
        prog.asset_total = 9
        prog.save()
        # Mark campaign retired to skip status change.
        camp.status = camp.Status.RETIRED  # type: ignore[attr-defined]
        camp.save()

        with mock.patch(
            "concordia.tasks.retirement.remove_next_project.delay"
        ) as m_delay:
            retire_campaign(camp.id)

        prog.refresh_from_db()
        self.assertEqual(prog.project_total, 7)
        self.assertEqual(prog.item_total, 8)
        self.assertEqual(prog.asset_total, 9)
        camp.refresh_from_db()
        self.assertEqual(camp.status, camp.Status.RETIRED)  # type: ignore[attr-defined]
        m_delay.assert_called_once_with(camp.id)

    def test_remove_next_project_calls_remove_next_item_when_project_exists(self):
        camp = create_campaign(slug="ret-c3")
        proj = create_project(campaign=camp, slug="ret-p3")
        create_campaign_retirement_progress(campaign=camp)

        with mock.patch("concordia.tasks.retirement.remove_next_item.delay") as m_delay:
            remove_next_project(camp.id)

        m_delay.assert_called_once_with(proj.id)

    def test_remove_next_project_marks_complete_when_no_projects(self):
        camp = create_campaign(slug="ret-c4")
        prog = create_campaign_retirement_progress(campaign=camp)

        with mock.patch("concordia.tasks.retirement.remove_next_item.delay") as m_delay:
            remove_next_project(camp.id)

        prog.refresh_from_db()
        self.assertTrue(prog.complete)
        self.assertIsNotNone(prog.completed_on)
        m_delay.assert_not_called()

    def test_project_removal_success_increments_and_triggers_next(self):
        camp = create_campaign(slug="ret-c5")
        prog = create_campaign_retirement_progress(campaign=camp)
        self.assertEqual(prog.projects_removed, 0)

        with mock.patch(
            "concordia.tasks.retirement.remove_next_project.delay"
        ) as m_delay:
            project_removal_success(project_id=123, campaign_id=camp.id)

        prog.refresh_from_db()
        self.assertEqual(prog.projects_removed, 1)
        self.assertTrue(any(e.get("id") == 123 for e in prog.removal_log))
        m_delay.assert_called_once_with(camp.id)

    def test_remove_next_item_calls_remove_next_assets_when_item_exists(self):
        camp = create_campaign(slug="ret-c6")
        proj = create_project(campaign=camp, slug="ret-p6")
        itm = create_item(project=proj, item_id="ret-i6")

        with mock.patch(
            "concordia.tasks.retirement.remove_next_assets.delay"
        ) as m_delay:
            remove_next_item(proj.id)

        m_delay.assert_called_once_with(itm.id)

    def test_remove_next_item_deletes_project_and_triggers_when_no_items(self):
        camp = create_campaign(slug="ret-c7")
        proj = create_project(campaign=camp, slug="ret-p7")

        with mock.patch(
            "concordia.tasks.retirement.project_removal_success.delay"
        ) as m_delay:
            remove_next_item(proj.id)

        with self.assertRaises(ObjectDoesNotExist):
            Project.objects.get(pk=proj.id)
        m_delay.assert_called_once_with(proj.id, camp.id)

    def test_assets_removal_success_updates_counts_and_triggers_next(self):
        camp = create_campaign(slug="ret-c8")
        prog = create_campaign_retirement_progress(campaign=camp)
        self.assertEqual(prog.assets_removed, 0)

        with mock.patch(
            "concordia.tasks.retirement.remove_next_assets.delay"
        ) as m_delay:
            assets_removal_success([10, 11, 12], campaign_id=camp.id, item_id=55)

        prog.refresh_from_db()
        self.assertEqual(prog.assets_removed, 3)
        self.assertTrue(any(e.get("id") == 10 for e in prog.removal_log))
        self.assertTrue(any(e.get("id") == 11 for e in prog.removal_log))
        self.assertTrue(any(e.get("id") == 12 for e in prog.removal_log))
        m_delay.assert_called_once_with(55)

    def test_remove_next_assets_when_no_assets_deletes_item_and_triggers(self):
        camp = create_campaign(slug="ret-c9")
        proj = create_project(campaign=camp, slug="ret-p9")
        itm = create_item(project=proj, item_id="ret-i9")

        with mock.patch(
            "concordia.tasks.retirement.item_removal_success.delay"
        ) as m_delay:
            remove_next_assets(itm.id)

        with self.assertRaises(ObjectDoesNotExist):
            # Item should be deleted.
            type(itm).objects.get(pk=itm.id)  # type: ignore[attr-defined]
        m_delay.assert_called_once_with(itm.id, camp.id, proj.id)

    def test_remove_next_assets_with_assets_uses_chord_in_chunks_of_10(self):
        camp = create_campaign(slug="ret-c10")
        proj = create_project(campaign=camp, slug="ret-p10")
        itm = create_item(project=proj, item_id="ret-i10")
        # Create 12 assets; only 10 should be in the chord header.
        ids = []
        for n in range(12):
            a = create_asset(item=itm, slug=f"ret-a10-{n}", sequence=n)
            ids.append(a.id)
        first_ten = list(
            Asset.objects.filter(item=itm)
            .order_by("id")
            .values_list("id", flat=True)[:10]
        )

        with (
            mock.patch("concordia.tasks.retirement.chord") as m_chord,
            mock.patch("concordia.tasks.retirement.delete_asset.s") as m_del_sig,
            mock.patch(
                "concordia.tasks.retirement.assets_removal_success.s"
            ) as m_body_sig,
        ):
            runner = mock.MagicMock()
            m_chord.return_value = runner
            m_del_sig.side_effect = lambda aid: f"S({aid})"
            m_body_sig.return_value = "BODY"

            remove_next_assets(itm.id)

            # Header should contain exactly 10 signatures, matching first ten ids.
            header_iter = m_chord.call_args[0][0]
            header_list = list(header_iter)
            self.assertEqual(header_list, [f"S({aid})" for aid in first_ten])
            # The body signature should be called with campaign and item ids.
            m_body_sig.assert_called_once_with(camp.id, itm.id)
            runner.assert_called_once_with("BODY")

    def test_delete_asset_deletes_storage_and_model_and_returns_id(self):
        itm = create_item(item_id="ret-i11")
        a = create_asset(item=itm, slug="ret-a11", sequence=11)

        with mock.patch("django.core.files.storage.FileSystemStorage.delete") as m_del:
            ret_id = delete_asset(a.id)

        self.assertEqual(ret_id, a.id)
        self.assertFalse(Asset.objects.filter(pk=a.id).exists())
        m_del.assert_called()

    def test_item_removal_success_increments_and_triggers_next(self):
        camp = create_campaign(slug="ret-c12")
        proj = create_project(campaign=camp, slug="ret-p12")
        itm = create_item(project=proj, item_id="ret-i12")
        prog = create_campaign_retirement_progress(campaign=camp)
        self.assertEqual(prog.items_removed, 0)

        with mock.patch("concordia.tasks.retirement.remove_next_item.delay") as m_delay:
            item_removal_success(
                item_id=itm.id, campaign_id=camp.id, project_id=proj.id
            )

        prog.refresh_from_db()
        self.assertEqual(prog.items_removed, 1)
        self.assertTrue(
            any(
                entry.get("type") == "item" and entry.get("id") == itm.id
                for entry in prog.removal_log
            )
        )
        m_delay.assert_called_once_with(proj.id)
