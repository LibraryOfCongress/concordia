# TODO: Add correct copyright header

import io
from unittest.mock import mock_open, patch

from django.test import TestCase

from importer.models import *
from importer.tasks import *
from importer.tests import mock_data


class MockResponse:
    """
    This class will be used by the mock to replace requests.get
    """

    def __init__(self, json_data, status_code, content=None, reason=" some error"):
        self.json_data = json_data
        self.status_code = status_code
        self.reason = reason
        self.content = content

    def json(self):
        return self.json_data

    def iter_content(self, chunk_size=None):
        return io.BytesIO(self.content.encode())


class GetItemIdFromItemURLTest(TestCase):
    def test_get_item_id_from_item_url_with_slash(self):
        """
        Testing get item id from item url if ends with /
        """
        # Arrange
        url = "https://www.loc.gov/item/mss859430021/"

        # Act
        resp = get_item_id_from_item_url(url)

        # Assert
        self.assertEqual(resp, "mss859430021")

    def test_get_item_id_from_item_url_without_slash(self):
        """
        Testing get item id from item url if ends without /
        """
        # Arrange
        url = "https://www.loc.gov/item/mss859430021"

        # Act
        resp = get_item_id_from_item_url(url)

        # Assert
        self.assertEqual(resp, "mss859430021")


class GETRequestDataTest(TestCase):
    def setUp(self):
        """
        Setting up the required test data input for importer tasks test cases
        :return:
        """
        self.url = "https://www.loc.gov/item/mss859430021?fo=json"

    @patch("importer.tasks.requests.get")  # Mock 'requests' module 'get' method.
    def test_get_request_success_json_data(self, mock_get):
        """get data on success json data"""

        # Arrange
        # Construct our mock response object, giving it relevant expected behaviours
        mock_resp_instance = MockResponse({"msg": "success"}, 200)
        mock_get.return_value = mock_resp_instance

        # Act
        response = get_request_data(self.url)

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(mock_resp_instance.status_code, 200)
        self.assertEqual(response, mock_resp_instance.json())

    @patch("importer.tasks.requests.get")  # Mock 'requests' module 'get' method.
    def test_get_request_not_success(self, mock_get):
        """get data on not success"""

        # Arrange
        # Construct our mock response object, giving it relevant expected behaviours
        mock_resp_instance = MockResponse({"msg": "bad request"}, 400)
        mock_get.return_value = mock_resp_instance

        # Act
        response = get_request_data(self.url)

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(mock_resp_instance.status_code, 400)
        self.assertEqual(response, {})

    @patch("importer.tasks.requests.get")  # Mock 'requests' module 'get' method.
    def test_get_request_normal_response(self, mock_get):
        """if json false return repose object with content"""

        # Arrange
        # Construct our mock response object, giving it relevant expected behaviours
        mock_resp_instance = MockResponse({"msg": "success"}, 200, content="abc")
        mock_get.return_value = mock_resp_instance

        # Act
        response = get_request_data(self.url, json_resp=False)

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(mock_resp_instance.status_code, 200)
        self.assertEqual(response, mock_resp_instance)


class GetCollectionPagesTest(TestCase):
    def setUp(self):
        """
        Setting up the required test data input for importer tasks test cases
        """
        self.url = "https://www.loc.gov/collections/branch-rickey-papers/?fa=partof:branch+rickey+papers:+baseball+file,+1906-1971"

    @patch("importer.tasks.requests.get")  # Mock 'requests' module 'get' method.
    def test_get_collection_pages(self, mock_get):
        """
        get collection pages successfully with pages info
        """
        # Arrange
        # Construct our mock response object, giving it relevant expected behaviours
        mock_resp_instance = MockResponse({"pagination": {"total": 10}}, 200)
        mock_get.return_value = mock_resp_instance

        # Act
        response = get_collection_pages(self.url)

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(mock_resp_instance.status_code, 200)
        self.assertEqual(response, 10)

    @patch("importer.tasks.requests.get")  # Mock 'requests' module 'get' method.
    def test_get_collection_sucess_no_pages(self, mock_get):
        """
        get collection pages successfully with no pages info
        """

        # Arrange
        # Construct our mock response object, giving it relevant expected behaviours
        mock_resp_instance = MockResponse({}, 200)
        mock_get.return_value = mock_resp_instance

        # Act
        response = get_collection_pages(self.url)

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(mock_resp_instance.status_code, 200)
        self.assertEqual(response, 0)


class GetCollectionItemidsTest(TestCase):
    def setUp(self):
        """
        Setting up the required test data input for importer tasks test cases
        """
        self.url = "https://www.loc.gov/collections/branch-rickey-papers/?fa=partof:branch+rickey+papers:+baseball+file,+1906-1971"

    @patch("importer.tasks.requests.get")  # Mock 'requests' module 'get' method.
    def test_get_collection_item_ids(self, mock_get):
        """
        Testing no of collection item ids available in given collection url
        """
        # Arrange
        mock_page1_result = MockResponse(mock_data.ITEM_IDS_DATA, 200)
        mock_page2_result = MockResponse({}, 200)
        mock_get.side_effect = [mock_page1_result, mock_page2_result]

        # Act
        response = get_collection_item_ids(self.url, 2)

        # Assert
        self.assertListEqual(response, ["mss37820001"])

    @patch("importer.tasks.requests.get")  # Mock 'requests' module 'get' method.
    def test_get_collection_item_ids_no_ids(self, mock_get):
        """
        Testing no of collection item ids not availabel collection url
        """
        # Arrange
        mock_page1_result = MockResponse({}, 200)
        mock_page2_result = MockResponse({}, 200)
        mock_get.side_effect = [mock_page1_result, mock_page2_result]

        # Act
        response = get_collection_item_ids(self.url, 2)

        # Arrange
        self.assertListEqual(response, [])


class GetCollectionItemAssetURLsTest(TestCase):
    def setUp(self):
        """
        Setting up the required test data input for importer tasks test cases
        """
        self.item_id = "mss37820001"

    @patch("importer.tasks.requests.get")  # Mock 'requests' module 'get' method.
    def test_get_collection_asset_urls(self, mock_get):
        """
        Testing no of collection item asset urls available in given item id
        """
        # Arrange
        mock_resp = MockResponse(mock_data.COLLECTION_ITEM_URLS_DATA, 200)
        mock_get.return_value = mock_resp

        # Act
        response = get_collection_item_asset_urls(self.item_id)

        # Assert
        self.assertListEqual(
            response,
            [
                "http://tile.loc.gov/image-services/iiif/service:mss:mss37820:mss37820-052:08:0001/full/pct:100/0/default.jpg"
            ],
        )

    @patch("importer.tasks.requests.get")  # Mock 'requests' module 'get' method.
    def test_get_collection_no_asset_urls(self, mock_get):
        """
        Testing no of collection item asset urls not available in given item id
        """
        # Arrange
        mock_resp = MockResponse({}, 200)
        mock_get.return_value = mock_resp

        # Act
        response = get_collection_item_asset_urls(self.item_id)

        # Assert
        self.assertListEqual(response, [])


class DownloadWriteCollcetionItemAssetTest(TestCase):
    @patch("importer.tasks.requests.get")  # Mock 'requests' module 'get' method.
    def test_download_write_asset_item(self, mock_get):
        """
        Testing download image and write into disk without error
        """
        # Arrange
        mock_resp = MockResponse({}, 200, content=mock_data.IMAZE_DATA)
        mock_get.return_value = mock_resp
        m = mock_open()

        with patch("__main__.open", m, create=True):

            # Act
            abc = download_write_collection_item_asset("dumy/image/url", "foo")

            # Assert
            self.assertEquals(abc, True)

    @patch("importer.tasks.requests.get")  # Mock 'requests' module 'get' method.
    def test_download_write_asset_item_error(self, mock_get):
        """
        Testing download image with exception
        """
        # Arrange
        mock_resp = MockResponse({}, 200, content=Exception("boom"))
        mock_get.return_value = mock_resp
        m = mock_open()

        with patch("__main__.open", m, create=True):

            # Act
            abc = download_write_collection_item_asset("dumy/image/url", "foo")

            # Assert
            self.assertEquals(abc, False)


class DownloadWriteCollectionItemAssetsTest(TestCase):
    def setUp(self):
        """
        Setting up the required test data input for importer tasks test cases
        """
        self.name = "branch-rickey-papers"
        self.project = "test-project"
        self.item_id = "mss37820001"
        self.url = "https://www.loc.gov/collections/branch-rickey-papers/?fa=partof:branch+rickey+papers:+baseball+file,+1906-1971"

    @patch("importer.tasks.get_save_item_assets")
    @patch("importer.tasks.requests.get")  # Mock 'requests' module 'get' method.
    def test_download_write_collection_item_asstes(self, mock_get, mock_save):
        """
        Testing no of collection item asset urls available in given collection url
        """
        # Arrange

        collection = {
            "collection_name": self.name,
            "collection_slug": slugify(self.name),
            "collection_task_id": "123",
            "subcollection_name": self.project,
            "subcollection_slug": slugify(self.project),
        }
        CollectionTaskDetails.objects.create(**collection)

        mock_resp_page = MockResponse({"pagination": {"total": 2}}, 200)
        mock_page1_result = MockResponse(mock_data.ITEM_IDS_DATA, 200)
        mock_page2_result = MockResponse({}, 200)
        mock_resp_item_urls = MockResponse(mock_data.COLLECTION_ITEM_URLS_DATA, 200)
        mock_get.side_effect = [
            mock_resp_page,
            mock_page1_result,
            mock_page2_result,
            mock_resp_item_urls,
        ]
        mock_save.return_value = None

        # Act
        download_write_collection_item_assets(self.name, self.project, self.url)

        ctd = CollectionTaskDetails.objects.get(
            collection_slug=self.name, subcollection_slug=self.project
        )
        ciac = CollectionItemAssetCount.objects.get(collection_task=ctd)

        # Assert
        self.assertEqual(ciac.collection_item_asset_count, 1)
        self.assertEqual(ciac.collection_item_identifier, self.item_id)
        self.assertEqual(ctd.collection_asset_count, 1)

    @patch("importer.tasks.get_save_item_assets")
    @patch("importer.tasks.requests.get")  # Mock 'requests' module 'get' method.
    def test_download_write_collection_item_asstes_no_db_entry(
        self, mock_get, mock_save
    ):
        """
        Testing no of collection item asset urls available in given collection url wiht no db entry in CollectionTaskDetails
        """
        # Arrange
        mock_resp_page = MockResponse({"pagination": {"total": 2}}, 200)
        mock_page1_result = MockResponse(mock_data.ITEM_IDS_DATA, 200)
        mock_page2_result = MockResponse({}, 200)
        mock_resp_item_urls = MockResponse(mock_data.COLLECTION_ITEM_URLS_DATA, 200)
        mock_get.side_effect = [
            mock_resp_page,
            mock_page1_result,
            mock_page2_result,
            mock_resp_item_urls,
        ]
        mock_save.return_value = None

        # Act
        download_write_collection_item_assets(self.name, self.project, self.url)

        ctd = CollectionTaskDetails.objects.get(
            collection_slug=self.name, subcollection_slug=self.project
        )
        ciac = CollectionItemAssetCount.objects.get(
            collection_task=ctd, collection_item_identifier=self.item_id
        )

        # Assert
        self.assertEqual(ciac.collection_item_asset_count, 1)
        self.assertEqual(ciac.collection_item_identifier, self.item_id)
        self.assertEqual(ctd.collection_asset_count, 1)


class DownloadWriteItemAssetsTest(TestCase):
    def setUp(self):
        """
        Setting up the required test data input for importer tasks test cases
        """
        self.name = "branch-rickey-papers"
        self.project = "test-project"
        self.item_id = "mss37820001"

    @patch("importer.tasks.get_save_item_assets")
    @patch("importer.tasks.requests.get")  # Mock 'requests' module 'get' method.
    def test_download_write_item_asstes(self, mock_get, mock_save):
        """
        Testing no of collection item asset urls available in given item id
        """
        # Arrange

        collection = {
            "collection_name": self.name,
            "collection_slug": slugify(self.name),
            "collection_task_id": "123",
            "subcollection_name": self.project,
            "subcollection_slug": slugify(self.project),
        }
        CollectionTaskDetails.objects.create(**collection)
        mock_resp = MockResponse(mock_data.COLLECTION_ITEM_URLS_DATA, 200)
        mock_get.return_value = mock_resp
        mock_save.return_value = None

        # Act
        download_write_item_assets(self.name, self.project, self.item_id)

        ctd = CollectionTaskDetails.objects.get(
            collection_slug=self.name, subcollection_slug=self.project
        )
        ciac = CollectionItemAssetCount.objects.get(
            collection_task=ctd, collection_item_identifier=self.item_id
        )

        # Assert
        self.assertEqual(ciac.collection_item_asset_count, 1)
        self.assertEqual(ciac.collection_item_identifier, self.item_id)
        self.assertEqual(ctd.collection_asset_count, 1)

    @patch("importer.tasks.get_save_item_assets")
    @patch("importer.tasks.requests.get")  # Mock 'requests' module 'get' method.
    def test_download_write_item_asstes_no_db_entry(self, mock_get, mock_save):
        """
        Testing no of collection item asset urls available in given item id wiht no db entry in CollectionTaskDetails
        """
        # Arrange
        mock_resp = MockResponse(mock_data.COLLECTION_ITEM_URLS_DATA, 200)
        mock_get.return_value = mock_resp
        mock_save.return_value = None

        # Act
        download_write_item_assets(self.name, self.project, self.item_id)

        ctd = CollectionTaskDetails.objects.get(
            collection_slug=self.name, subcollection_slug=self.project
        )
        ciac = CollectionItemAssetCount.objects.get(
            collection_task=ctd, collection_item_identifier=self.item_id
        )

        # Assert
        self.assertEqual(ciac.collection_item_asset_count, 1)
        self.assertEqual(ciac.collection_item_identifier, self.item_id)
        self.assertEqual(ctd.collection_asset_count, 1)
