import tempfile  # NEW
from types import SimpleNamespace
from unittest import mock

from django.test import TestCase

import concordia.celery as celery_mod
from concordia.celery import import_all_submodules


class ConcordiaCeleryTests(TestCase):
    def test_returns_early_for_non_package(self):
        mock_pkg = SimpleNamespace(__name__="not_a_pkg")  # no __path__

        with (
            mock.patch.object(
                celery_mod.importlib, "import_module", return_value=mock_pkg
            ) as mock_import,
            mock.patch.object(celery_mod.pkgutil, "walk_packages") as mock_walk,
        ):
            import_all_submodules("not_a_pkg")

        mock_import.assert_called_once_with("not_a_pkg")
        mock_walk.assert_not_called()

    def test_imports_all_submodules_for_package(self):
        sub1 = SimpleNamespace(name="dummy_pkg.sub1")
        sub2 = SimpleNamespace(name="dummy_pkg.sub2")

        with tempfile.TemporaryDirectory() as td:
            mock_pkg = SimpleNamespace(__name__="dummy_pkg", __path__=[td])

            with (
                mock.patch.object(celery_mod.importlib, "import_module") as mock_import,
                mock.patch.object(
                    celery_mod.pkgutil, "walk_packages", return_value=[sub1, sub2]
                ) as mock_walk,
            ):

                def side_effect(name):
                    if name == "dummy_pkg":
                        return mock_pkg
                    return SimpleNamespace(__name__=name)

                mock_import.side_effect = side_effect
                import_all_submodules("dummy_pkg")

        mock_walk.assert_called_once()
        args, _kwargs = mock_walk.call_args
        self.assertEqual(args[0], mock_pkg.__path__)
        self.assertEqual(args[1], mock_pkg.__name__ + ".")

        self.assertIn(mock.call("dummy_pkg"), mock_import.mock_calls)
        self.assertIn(mock.call("dummy_pkg.sub1"), mock_import.mock_calls)
        self.assertIn(mock.call("dummy_pkg.sub2"), mock_import.mock_calls)

    def test_package_with_no_submodules(self):
        with tempfile.TemporaryDirectory() as td:
            mock_pkg = SimpleNamespace(__name__="empty_pkg", __path__=[td])

            with (
                mock.patch.object(celery_mod.importlib, "import_module") as mock_import,
                mock.patch.object(
                    celery_mod.pkgutil, "walk_packages", return_value=[]
                ) as mock_walk,
            ):

                mock_import.side_effect = lambda name: (
                    mock_pkg if name == "empty_pkg" else SimpleNamespace(__name__=name)
                )
                import_all_submodules("empty_pkg")

        mock_walk.assert_called_once()
        mock_import.assert_called_once_with("empty_pkg")
