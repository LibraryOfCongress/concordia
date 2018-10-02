from django.test import TestCase

from ..tasks import get_item_id_from_item_url, normalize_collection_url


class GetItemIdFromItemURLTests(TestCase):
    def test_get_item_id_from_item_url_with_slash(self):
        """
        Testing get item id from item url if ends with /
        """

        url = "https://www.loc.gov/item/mss859430021/"
        resp = get_item_id_from_item_url(url)
        self.assertEqual(resp, "mss859430021")

    def test_get_item_id_from_item_url_without_slash(self):
        """
        Testing get item id from item url if ends without /
        """

        url = "https://www.loc.gov/item/mss859430021"
        resp = get_item_id_from_item_url(url)
        self.assertEqual(resp, "mss859430021")


class CollectionURLNormalizationTests(TestCase):
    def test_basic_normalization(self):
        self.assertEqual(
            normalize_collection_url(
                "https://www.loc.gov/collections/branch-rickey-papers/"
            ),
            "https://www.loc.gov/collections/branch-rickey-papers/?fo=json",
        )

    def test_extra_querystring_parameters(self):
        self.assertEqual(
            normalize_collection_url(
                "https://www.loc.gov/collections/branch-rickey-papers/?foo=bar"
            ),
            "https://www.loc.gov/collections/branch-rickey-papers/?fo=json&foo=bar",
        )

    def test_conflicting_querystring_parameters(self):
        self.assertEqual(
            normalize_collection_url(
                "https://www.loc.gov/collections/branch-rickey-papers/?foo=bar&fo=xml&sp=99&at=item"
            ),
            "https://www.loc.gov/collections/branch-rickey-papers/?fo=json&foo=bar",
        )
