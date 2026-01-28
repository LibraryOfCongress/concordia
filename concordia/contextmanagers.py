# Based on code from
# https://docs.celeryq.dev/en/v5.5.0/tutorials/task-cookbook.html#ensuring-a-task-is-only-executed-one-at-a-time

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager

from django.core.cache import cache

logger = logging.getLogger(__name__)

DEFAULT_LOCK_DURATION = 60 * 10  # 10 minutes


@contextmanager
def cache_lock(
    lock_id: str,
    oid: str,
    lock_duration: int = DEFAULT_LOCK_DURATION,
) -> Generator[bool, None, None]:
    """
    Context manager to acquire a distributed cache-based lock.

    Ensures that only one process or thread can execute a block of code
    associated with a given lock ID at a time. Uses Django's cache backend
    and `cache.add` to store the lock key, then `cache.delete` to release the
    lock when exiting the context if it was acquired and has not expired.

    Args:
        lock_id (str): Unique key identifying the lock in the cache.
        oid (str): Identifier for the owner of the lock. Stored as the cache
            value but not otherwise used.
        lock_duration (int): How long to hold the lock in seconds. Defaults
            to 10 minutes.

    Yields:
        bool: True if the lock was acquired, False otherwise.

    Usage:
        with cache_lock("my-task-lock", "worker-1") as acquired:
            if acquired:
                # Do protected work here
            else:
                # Skip or retry later
    """
    try:
        timeout_at = time.monotonic() + lock_duration
        # cache.add does nothing and returns False if the key already exists
        status = cache.add(lock_id, oid, lock_duration)
        yield status
    finally:
        if status and time.monotonic() < timeout_at:
            # Don't release the lock if we did not acquire it
            # Also, don't release the lock if we exceeded the timeout
            # to reduce the chance of releasing an expired lock
            # owned by someone else
            cache.delete(lock_id)
