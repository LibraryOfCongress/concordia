from unittest import TestCase
from unittest.mock import MagicMock, patch

from celery import Task

from concordia.decorators import locked_task


class LockedTaskDecoratorTests(TestCase):
    def setUp(self):
        self.hostname = "test-worker"
        self.logger_patch = patch("concordia.decorators.logger")
        self.logger = self.logger_patch.start()
        self.addCleanup(self.logger_patch.stop)

        self.cache_lock_patch = patch("concordia.decorators.cache_lock")
        self.mock_cache_lock = self.cache_lock_patch.start()
        self.addCleanup(self.cache_lock_patch.stop)

    def make_task_instance(self, name="test-task"):
        task = MagicMock(spec=Task)
        task.name = name
        task.request.hostname = self.hostname
        return task

    def test_lock_by_args_allows_only_one_execution(self):
        task = self.make_task_instance()

        calls = []

        @locked_task
        def dummy(self, arg):
            calls.append(arg)
            return f"Ran with {arg}"

        dummy_task = dummy.__get__(task)

        self.mock_cache_lock.return_value.__enter__.return_value = True
        result = dummy_task("foo")
        self.assertEqual(result, "Ran with foo")
        self.assertEqual(calls, ["foo"])

        self.mock_cache_lock.return_value.__enter__.return_value = False
        result = dummy_task("foo")
        self.assertIsNone(result)
        self.logger.info.assert_called_once()

    def test_lock_by_task_name(self):
        task = self.make_task_instance()

        calls = []

        @locked_task(lock_by_args=False)
        def dummy(self, arg):
            calls.append(arg)
            return f"Ran with {arg}"

        dummy_task = dummy.__get__(task)

        self.mock_cache_lock.return_value.__enter__.return_value = True
        result = dummy_task("foo")
        self.assertEqual(result, "Ran with foo")
        self.assertEqual(calls, ["foo"])

    def test_force_runs_even_if_lock_not_acquired(self):
        task = self.make_task_instance()

        calls = []

        @locked_task
        def dummy(self, arg):
            calls.append(arg)
            return f"Forced {arg}"

        dummy_task = dummy.__get__(task)

        self.mock_cache_lock.return_value.__enter__.return_value = False
        result = dummy_task("bar", force=True)
        self.assertEqual(result, "Forced bar")
        self.logger.warning.assert_called_once()

    def test_error_in_key_generation_logs_and_raises(self):
        task = self.make_task_instance()

        @locked_task
        def dummy(self, arg):
            return "This shouldn't run"

        dummy_task = dummy.__get__(task)

        # Use a non-repr-able object to simulate key generation failure
        class Unreprable:
            def __repr__(self):
                raise ValueError("Can't repr")

        with self.assertRaises(ValueError):
            dummy_task(Unreprable())

        self.logger.exception.assert_called_once_with(
            "Unable to create cache key from arguments for %s.", task.name
        )
