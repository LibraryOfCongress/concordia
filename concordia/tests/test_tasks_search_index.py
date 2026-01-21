from unittest import mock

from django.test import TestCase

from concordia.tasks.search_index import (
    create_opensearch_indices,
    delete_opensearch_indices,
    populate_opensearch_assets_indices,
    populate_opensearch_indices,
    populate_opensearch_users_indices,
    rebuild_opensearch_indices,
)


class SearchIndexTasksTests(TestCase):
    def test_create_opensearch_indices_calls_management_command(self):
        with mock.patch("concordia.tasks.search_index.call_command") as m_call:
            result = create_opensearch_indices()
            self.assertIsNone(result)
            m_call.assert_called_once_with(
                "opensearch",
                "index",
                "create",
                verbosity=2,
                force=True,
                ignore_error=True,
            )

    def test_delete_opensearch_indices_calls_management_command(self):
        with mock.patch("concordia.tasks.search_index.call_command") as m_call:
            result = delete_opensearch_indices()
            self.assertIsNone(result)
            m_call.assert_called_once_with(
                "opensearch", "index", "delete", force=True, ignore_error=True
            )

    def test_rebuild_opensearch_indices_calls_management_command(self):
        with mock.patch("concordia.tasks.search_index.call_command") as m_call:
            result = rebuild_opensearch_indices()
            self.assertIsNone(result)
            m_call.assert_called_once_with(
                "opensearch",
                "index",
                "rebuild",
                verbosity=2,
                force=True,
                ignore_error=True,
            )

    def test_populate_users_indices_calls_management_command(self):
        with mock.patch("concordia.tasks.search_index.call_command") as m_call:
            result = populate_opensearch_users_indices()
            self.assertIsNone(result)
            m_call.assert_called_once_with(
                "opensearch",
                "document",
                "index",
                "--indices",
                "users",
                "--force",
                "--parallel",
            )

    def test_populate_assets_indices_calls_management_command(self):
        with mock.patch("concordia.tasks.search_index.call_command") as m_call:
            result = populate_opensearch_assets_indices()
            self.assertIsNone(result)
            m_call.assert_called_once_with(
                "opensearch",
                "document",
                "index",
                "--indices",
                "assets",
                "--force",
                "--parallel",
            )

    def test_populate_all_indices_calls_management_command(self):
        with mock.patch("concordia.tasks.search_index.call_command") as m_call:
            result = populate_opensearch_indices()
            self.assertIsNone(result)
            m_call.assert_called_once_with(
                "opensearch", "document", "index", "--force", "--parallel"
            )
