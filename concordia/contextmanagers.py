# Based on code from
# https://docs.celeryq.dev/en/v5.5.0/tutorials/task-cookbook.html#ensuring-a-task-is-only-executed-one-at-a-time

import logging
import time
from contextlib import contextmanager

from django.core.cache import cache

logger = logging.getLogger(__name__)

DEFAULT_LOCK_DURATION = 60 * 10  # 10 minutes


@contextmanager
def cache_lock(lock_id, oid, lock_duration=DEFAULT_LOCK_DURATION):
    try:
        timeout_at = time.monotonic() + lock_duration
        # cache.add does nothing and returns False if the key already exists
        status = cache.add(lock_id, oid, lock_duration)
        yield status
    finally:
        if status and time.monotonic() < timeout_at:
            # Don't release the lock if we didn't acquire it
            # Also, don't release the lock if we exceeded the timeout
            # to reduce the chance of releasing an expired lock
            # owned by someone else
            cache.delete(lock_id)
