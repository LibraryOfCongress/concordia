import logging
from unittest import mock

from django.test import TestCase

from importer.logging import CeleryTaskIDFilter


class CeleryTaskIDFilterTests(TestCase):
    def setUp(self):
        self.filter = CeleryTaskIDFilter()
        self.record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test",
            lineno=10,
            msg="Test log message",
            args=(),
            exc_info=None,
        )

    @mock.patch("importer.logging.current_task")
    def test_filter_with_task_id(self, mock_task):
        mock_task.request.id = "1234-abcd"

        result = self.filter.filter(self.record)

        self.assertTrue(result)  # Ensure the log record is not discarded
        self.assertEqual(self.record.task_id, "/[1234-abcd]")

    @mock.patch("importer.logging.current_task")
    def test_filter_without_task(self, mock_task):
        mock_task.request.id = None

        result = self.filter.filter(self.record)

        self.assertTrue(result)
        self.assertEqual(self.record.task_id, "")

    @mock.patch("importer.logging.current_task", None)
    def test_filter_with_no_current_task(self):
        result = self.filter.filter(self.record)

        self.assertTrue(result)
        self.assertEqual(self.record.task_id, "")
