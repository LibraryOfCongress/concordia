import concurrent.futures
from unittest import mock

from django.test import TestCase

from importer.tasks import fetch_all_urls


class FetchAllUrlsTests(TestCase):
    @mock.patch.object(concurrent.futures.ThreadPoolExecutor, "map")
    def test_fetch_all_urls(self, mock_map):
        output = "https://www.loc.gov/item/mss859430021/ - Asset Count: 0"
        mock_map.return_value = ((output, 0),)
        finals, totals = fetch_all_urls(
            [
                "https://www.loc.gov/item/mss859430021/",
            ]
        )
        self.assertEqual(finals, [output])
        self.assertEqual(totals, 0)
