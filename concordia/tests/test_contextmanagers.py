from unittest import TestCase
from unittest.mock import patch

from concordia.contextmanagers import DEFAULT_LOCK_DURATION, cache_lock


class CacheLockTests(TestCase):
    def setUp(self):
        self.lock_id = "test-lock"
        self.oid = "worker-1"

        self.cache_patch = patch("concordia.contextmanagers.cache")
        self.mock_cache = self.cache_patch.start()
        self.addCleanup(self.cache_patch.stop)

        self.time_patch = patch("concordia.contextmanagers.time.monotonic")
        self.mock_monotonic = self.time_patch.start()
        self.addCleanup(self.time_patch.stop)

        self.start_time = 100.0
        self.mock_monotonic.return_value = self.start_time

    def test_acquires_and_releases_lock(self):
        self.mock_cache.add.return_value = True

        with cache_lock(self.lock_id, self.oid) as acquired:
            self.assertTrue(acquired)
            self.mock_cache.add.assert_called_once_with(
                self.lock_id, self.oid, DEFAULT_LOCK_DURATION
            )

        self.mock_cache.delete.assert_called_once_with(self.lock_id)

    def test_does_not_release_if_lock_not_acquired(self):
        self.mock_cache.add.return_value = False

        with cache_lock(self.lock_id, self.oid) as acquired:
            self.assertFalse(acquired)

        self.mock_cache.delete.assert_not_called()

    def test_does_not_release_if_expired(self):
        self.mock_cache.add.return_value = True

        # Simulate expiration: time has passed beyond timeout
        def advance_time():
            return self.start_time + DEFAULT_LOCK_DURATION + 1

        self.mock_monotonic.side_effect = [self.start_time, advance_time()]

        with cache_lock(self.lock_id, self.oid) as acquired:
            self.assertTrue(acquired)

        self.mock_cache.delete.assert_not_called()
