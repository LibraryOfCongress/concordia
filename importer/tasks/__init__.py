"""
See the module-level docstring for implementation details
"""

import concurrent.futures
from logging import getLogger

from .items import import_item_count_from_url

logger = getLogger(__name__)


def fetch_all_urls(items):
    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
        result = executor.map(import_item_count_from_url, items)
    finals = []
    totals = 0

    for value, score in result:
        totals = totals + score
        finals.append(value)

    return finals, totals
