from types import SimpleNamespace
from unittest import mock

from django.test import TestCase

from concordia.utils.celery import get_registered_task


class CeleryUtilsTests(TestCase):
    def test_get_registered_task_returns_task_from_registry(self):
        name = "pkg.tasks.do_thing"
        dummy_task = object()
        app = SimpleNamespace(tasks={name: dummy_task}, send_task=mock.Mock())

        with mock.patch(
            "concordia.utils.celery.concordia_celery_app",
            app,
        ):
            got = get_registered_task(name)

        self.assertIs(got, dummy_task)
        app.send_task.assert_not_called()

    def test_get_registered_task_raises_runtime_error_with_cause(self):
        name = "pkg.tasks.missing"
        app = SimpleNamespace(tasks={}, send_task=mock.Mock())

        with mock.patch(
            "concordia.utils.celery.concordia_celery_app",
            app,
        ):
            with self.assertRaises(RuntimeError) as ctx:
                get_registered_task(name)

        message = str(ctx.exception)
        self.assertIn(f"Task {name} is not registered.", message)
        self.assertIn("Did you typo it?", message)
        self.assertIsInstance(ctx.exception.__cause__, KeyError)
        app.send_task.assert_not_called()
