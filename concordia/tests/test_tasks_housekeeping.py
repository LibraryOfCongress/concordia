from unittest import mock

from django.test import TestCase

from concordia.tasks.housekeeping import clear_sessions


class ClearSessionsTaskTests(TestCase):
    def test_calls_django_clearsessions_command(self):
        # Verify the task invokes Django's clearsessions management command.
        with mock.patch("concordia.tasks.housekeeping.call_command") as mock_call:
            result = clear_sessions()
            self.assertIsNone(result)
            mock_call.assert_called_once_with("clearsessions")

    def test_raises_when_call_command_fails(self):
        # Ensure exceptions from the management command propagate.
        with mock.patch(
            "concordia.tasks.housekeeping.call_command",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                clear_sessions()
