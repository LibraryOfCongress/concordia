from unittest import mock

from django.test import TestCase
from django.utils import timezone

from importer.models import ImportJob
from importer.tasks.decorators import update_task_status
from importer.tests.utils import create_import_job


class TaskDecoratorTests(TestCase):
    def test_update_task_status(self):
        def test_function(self, task_status_object, raise_exception=False):
            task_status_object.test_function_ran = True
            if raise_exception:
                raise Exception("Test Exception")
            task_status_object.test_function_finished = True

        wrapped_test_function = update_task_status(test_function)

        # We create this non-mocked completed job here to use in a later test
        # because we can't easily do this once we mock ImportJob.save
        test_job = create_import_job(completed=timezone.now())

        # We can't just mock the entire model here or use easily use a custom
        # class because update_task_status depends on Django model internals,
        # particularly __class__._default_manager. __class__ cannot be overriden
        # (it points to MagicMock), Model._default_manager cannot be set directly
        # and mocking Model.objects does not cause called on Model._default_manager
        # to properly use the mock--it continues to use the actual Model.objects
        with mock.patch.multiple(
            ImportJob,
            save=mock.MagicMock(),
            __str__=mock.MagicMock(return_value="Mock Job"),
        ):
            job = ImportJob()
            wrapped_test_function(mock.MagicMock(), job)
            self.assertTrue(hasattr(job, "test_function_ran"))
            self.assertTrue(job.test_function_ran)
            self.assertTrue(hasattr(job, "test_function_finished"))
            self.assertTrue(job.test_function_finished)
            self.assertNotEqual(job.last_started, None)
            self.assertNotEqual(job.task_id, None)
            self.assertTrue(job.completed)
            self.assertTrue(job.save.called)

            ImportJob.save.reset_mock()
            job2 = ImportJob()
            job2.status = "Original Status"
            with self.assertRaisesRegex(Exception, "Test Exception"):
                wrapped_test_function(mock.MagicMock(), job2, True)
            self.assertTrue(hasattr(job2, "test_function_ran"))
            self.assertTrue(job2.test_function_ran)
            self.assertFalse(hasattr(job2, "test_function_finished"))
            self.assertNotEqual(job2.last_started, None)
            self.assertNotEqual(job2.task_id, None)
            self.assertFalse(job2.completed)
            self.assertTrue(job2.save.called)
            self.assertEqual(
                job2.status, "Original Status\n\nUnhandled exception: Test Exception"
            )

            ImportJob.save.reset_mock()
            job3 = ImportJob()
            job3.id = test_job.id
            with self.assertLogs("importer.tasks", level="WARNING") as log:
                wrapped_test_function(mock.MagicMock(), job3)
                self.assertEqual(
                    log.output,
                    [
                        "WARNING:importer.tasks.decorators:Task Mock Job was "
                        "already completed and will not be repeated"
                    ],
                )
            self.assertFalse(hasattr(job3, "test_function_ran"))
            self.assertFalse(hasattr(job3, "test_function_finished"))
            self.assertEqual(job3.last_started, None)
            self.assertEqual(job3.task_id, None)
            self.assertFalse(job3.completed)
            self.assertFalse(job3.save.called)
