import concurrent.futures
from logging import getLogger
from typing import Iterable

from .items import import_item_count_from_url

logger = getLogger(__name__)


def fetch_all_urls(items: Iterable[str]) -> tuple[list[str], int]:
    """
    Fetch counts for many item URLs concurrently.

    Uses a thread pool to call ``import_item_count_from_url`` for each input
    URL. Aggregates the returned values and the total score.

    Args:
        items: Iterable of item URLs.

    Returns:
        A 2-tuple of:
            - list of values returned for each URL, in the map order
            - integer sum of all scores
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
        result = executor.map(import_item_count_from_url, items)

    finals: list[str] = []
    totals: int = 0

    for value, score in result:
        totals += score
        finals.append(value)

    return finals, totals
