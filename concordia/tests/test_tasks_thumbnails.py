from unittest import mock

from django.test import TestCase

from concordia.tasks.thumbnails import (
    download_item_thumbnail_task,
    download_missing_thumbnails_task,
)

from .utils import create_campaign, create_item, create_project


class ThumbnailsTasksTests(TestCase):
    def test_download_item_thumbnail_task_returns_skip_when_no_url(self):
        # Item has no thumbnail_url; task should return skip message.
        proj = create_project(campaign=create_campaign(slug="t-c1"), slug="t-p1")
        item = create_item(project=proj, item_id="t-i1", thumbnail_url="")

        with mock.patch("importer.tasks.items.download_and_set_item_thumbnail") as m_dl:
            result = download_item_thumbnail_task.run(item.id, force=False)

        self.assertEqual(result, "No thumbnail URL available.")
        m_dl.assert_not_called()

    def test_download_item_thumbnail_task_calls_helper_with_force(self):
        # Item has a thumbnail_url; helper should be called with force flag.
        proj = create_project(campaign=create_campaign(slug="t-c2"), slug="t-p2")
        item = create_item(
            project=proj,
            item_id="t-i2",
            thumbnail_url="https://ex.invalid/t.jpg",
            thumbnail_image="",
        )

        with mock.patch("importer.tasks.items.download_and_set_item_thumbnail") as m_dl:
            m_dl.return_value = "stored/path/t.jpg"
            result = download_item_thumbnail_task.run(item.id, force=True)

        self.assertEqual(result, "stored/path/t.jpg")
        m_dl.assert_called_once()
        # First arg is the Item instance, second the source URL.
        args, kwargs = m_dl.call_args
        self.assertEqual(args[0].id, item.id)
        self.assertEqual(args[1], "https://ex.invalid/t.jpg")
        self.assertTrue(kwargs.get("force"))

    def test_download_missing_thumbnails_task_returns_zero_when_none(self):
        # No items meet the filter; should log and return 0, no group calls.
        with mock.patch("concordia.tasks.thumbnails.group") as m_group:
            count = download_missing_thumbnails_task.run()

        self.assertEqual(count, 0)
        m_group.assert_not_called()

    def test_download_missing_thumbnails_task_filters_and_batches_once(self):
        from unittest import mock

        camp = create_campaign(slug="t-c3")
        proj_a = create_project(campaign=camp, slug="t-p3a")
        proj_b = create_project(campaign=camp, slug="t-p3b")

        i1 = create_item(
            project=proj_a,
            item_id="t-i3-1",
            thumbnail_url="http://example.com/img1.jpg",
            thumbnail_image="",
        )
        i2 = create_item(
            project=proj_a,
            item_id="t-i3-2",
            thumbnail_url="http://example.com/img2.jpg",
            thumbnail_image="",
        )
        create_item(  # wrong project -> not eligible
            project=proj_b,
            item_id="t-i3-3",
            thumbnail_url="http://example.com/img3.jpg",
            thumbnail_image="",
        )
        create_item(  # already has image -> not eligible
            project=proj_a,
            item_id="t-i3-4",
            thumbnail_url="http://example.com/img4.jpg",
            thumbnail_image="has-file",
        )

        with (
            mock.patch("concordia.tasks.thumbnails.group") as m_group,
            mock.patch(
                "concordia.tasks.thumbnails.download_item_thumbnail_task.s"
            ) as m_sig,
        ):
            runner = mock.MagicMock()
            runner.apply_async.return_value.get.return_value = None

            def fake_group(header_iter):
                # Force generator evaluation so .s(...) is actually called.
                list(header_iter)
                return runner

            m_group.side_effect = fake_group

            count = download_missing_thumbnails_task.run(
                project_id=proj_a.id, batch_size=2, limit=10, force=True
            )

        self.assertEqual(count, 2)
        m_sig.assert_has_calls(
            [mock.call(i1.id, force=True), mock.call(i2.id, force=True)],
            any_order=False,
        )
        m_group.assert_called_once()
        runner.apply_async.assert_called_once()
        runner.apply_async.return_value.get.assert_called_once_with(
            disable_sync_subtasks=False
        )

    def test_download_missing_thumbnails_task_multiple_waves(self):
        from unittest import mock

        camp = create_campaign(slug="t-c4")
        proj = create_project(campaign=camp, slug="t-p4")
        items = [
            create_item(
                project=proj,
                item_id=f"t-i4-{n}",
                thumbnail_url=f"http://example.com/{n}.jpg",
                thumbnail_image="",
            )
            for n in range(5)
        ]

        with (
            mock.patch("concordia.tasks.thumbnails.group") as m_group,
            mock.patch(
                "concordia.tasks.thumbnails.download_item_thumbnail_task.s"
            ) as m_sig,
        ):
            runners = [mock.MagicMock() for _ in range(3)]
            for r in runners:
                r.apply_async.return_value.get.return_value = None
            it = iter(runners)

            def fake_group(header_iter):
                # Force generator consumption each wave.
                list(header_iter)
                return next(it)

            m_group.side_effect = fake_group

            count = download_missing_thumbnails_task.run(
                project_id=proj.id, batch_size=2, limit=None, force=False
            )

        self.assertEqual(count, 5)
        self.assertEqual(m_group.call_count, 3)
        expected = [mock.call(itm.id, force=False) for itm in items]
        self.assertEqual(m_sig.call_args_list, expected)
