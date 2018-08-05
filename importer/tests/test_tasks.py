# TODO: Add correct copyright header

from unittest.mock import patch

from django.template.defaultfilters import slugify
from django.test import TestCase

from importer.tasks import *
from importer.tests import mock_data
from importer.models import *


class MockResponse:
    """
    This class will be used by the mock to replace requests.get
    """

    def __init__(self, json_data, status_code, reason=" some error"):
        self.json_data = json_data
        self.status_code = status_code
        self.reason = reason

    def json(self):
        return self.json_data


class GETRequestDataTest(TestCase):

    def setUp(self):
        """
        Setting up the required test data input for importer tasks test cases
        :return:
        """
        self.url = 'https://www.loc.gov/item/mss859430021?fo=json'

    @patch('importer.tasks.requests.get')  # Mock 'requests' module 'get' method.
    def test_get_request_data(self, mock_get):
        """get data on direct hit"""

        # Arrange
        # Construct our mock response object, giving it relevant expected behaviours
        mock_resp_instance = MockResponse({"msg": "success"}, 200)
        mock_get.return_value = mock_resp_instance

        # Act
        response = get_request_data(self.url)

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(mock_resp_instance.status_code, 200)
        self.assertEqual(response, mock_resp_instance.json())

    @patch('importer.tasks.requests.get')  # Mock 'requests' module 'get' method.
    def test_get_request_data_retry_once(self, mock_get):
        """get data on first retry"""

        # Arrange
        # Construct our mock response object, giving it relevant expected behaviours
        mock_resp_instance_fail = MockResponse({"msg": "bad request"}, 400)
        mock_resp_instance_successs = MockResponse({"msg": "success"}, 200)
        mock_get.side_effect = [mock_resp_instance_fail, mock_resp_instance_successs]

        # Act
        response = get_request_data(self.url)

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(mock_resp_instance_fail.status_code, 400)
        self.assertEqual(mock_resp_instance_successs.status_code, 200)
        self.assertEqual(response, mock_resp_instance_successs.json())

    @patch('importer.tasks.requests.get')  # Mock 'requests' module 'get' method.
    def test_get_request_data_retry_more(self, mock_get):
        """Always failing then 3 retry returning empty with logger error"""

        # Arrange
        # Construct our mock response object, giving it relevant expected behaviours
        mock_resp_instance_fail = MockResponse({"msg": "bad request"}, 400)
        mock_get.side_effect = [mock_resp_instance_fail, mock_resp_instance_fail, mock_resp_instance_fail, mock_resp_instance_fail]

        # Act
        response = get_request_data(self.url)

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(mock_resp_instance_fail.status_code, 400)
        self.assertEqual(response, {})


class GetCollectionParamsTest(TestCase):

    def test_get_collection_params_without_fa(self):
        """
        Testing params of given collection url
        """
        # Arrange
        url = 'https://www.loc.gov/item/mss859430021?fo=json'

        # Act
        curl, cparams = get_collection_params(url)

        # Assert
        self.assertEqual(curl, url)
        self.assertEqual(cparams, {})

    def test_get_collection_params_with_fa(self):
        """
        Testing params of given invalid collection url
        """
        # Arrange
        test_url = 'https://www.loc.gov/collections/branch-rickey-papers/?fa=partof:branch+rickey+papers:+baseball+file,+1906-1971'

        # Act
        curl, cparams = get_collection_params(test_url)

        # Assert
        self.assertEqual(curl, test_url.split("?fa")[0])
        self.assertEqual(cparams.get('fa'), "partof:branch+rickey+papers:+baseball+file,+1906-1971")


class GetCollectionPagesTest(TestCase):

    def setUp(self):
        """
        Setting up the required test data input for importer tasks test cases
        """
        self.url = 'https://www.loc.gov/collections/branch-rickey-papers/?fa=partof:branch+rickey+papers:+baseball+file,+1906-1971'

    @patch('importer.tasks.requests.get')  # Mock 'requests' module 'get' method.
    def test_get_collection_pages(self, mock_get):
        """
        get collection pages successfully with pages info
        """
        # Arrange
        # Construct our mock response object, giving it relevant expected behaviours
        mock_resp_instance = MockResponse({"pagination": {"total":10}}, 200)
        mock_get.return_value = mock_resp_instance

        # Act
        response = get_collection_pages(self.url)

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(mock_resp_instance.status_code, 200)
        self.assertEqual(response, 10)

    @patch('importer.tasks.requests.get')  # Mock 'requests' module 'get' method.
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
        self.url = 'https://www.loc.gov/collections/branch-rickey-papers/?fa=partof:branch+rickey+papers:+baseball+file,+1906-1971'
        self.name = 'branch-rickey-papers'

    @patch('importer.tasks.requests.get')  # Mock 'requests' module 'get' method.
    def test_get_collection_item_ids(self, mock_get):
        """
        Testing no of collection item ids available in given collection url
        """
        # Arrange
        collection = {"collection_name": self.name, "collection_slug": slugify(self.name), "collection_task_id": "123"}
        CollectionTaskDetails.objects.create(**collection)
        mock_resp_pages = MockResponse({"pagination": {"total":2}}, 200)
        mock_page1_result = MockResponse(mock_data.ITEM_IDS_DATA, 200)
        mock_page2_result = MockResponse({}, 200)
        mock_get.side_effect = [mock_resp_pages, mock_page1_result, mock_page2_result]

        # Act
        response = get_collection_item_ids(self.name, self.url)

        ctd = CollectionTaskDetails.objects.get(collection_slug=self.name)

        # Assert
        self.assertEqual(ctd.collection_page_count,2)
        self.assertEqual(ctd.collection_item_count,1)
        self.assertListEqual(response,['mss37820001'])

    @patch('importer.tasks.requests.get')  # Mock 'requests' module 'get' method.
    def test_get_collection_item_ids_no_ids(self, mock_get):
        """
        Testing no of collection item ids not availabel collection url
        """
        # Arrange
        mock_resp_pages = MockResponse({"pagination": {"total":2}}, 200)
        mock_page1_result = MockResponse({}, 200)
        mock_page2_result = MockResponse({}, 200)
        mock_get.side_effect = [mock_resp_pages, mock_page1_result, mock_page2_result]

        # Act
        response = get_collection_item_ids(self.name, self.url)

        # Arrange
        self.assertEqual(response.data, {"message": 'No page results found for collection : "%s" from loc API' % self.url})

    @patch('importer.tasks.requests.get')  # Mock 'requests' module 'get' method.
    def test_get_collection_item_ids_no_db_entry(self, mock_get):
        """
        Testing no of collection item ids with out collectiontsakdetails db entry collection url
        """
        # Arrange
        mock_resp_pages = MockResponse({"pagination": {"total":2}}, 200)
        mock_page1_result = MockResponse(mock_data.ITEM_IDS_DATA, 200)
        mock_page2_result = MockResponse({}, 200)
        mock_get.side_effect = [mock_resp_pages, mock_page1_result, mock_page2_result]

        # Act
        response = get_collection_item_ids(self.name, self.url)

        # Arrange
        self.assertEqual(response.data, {"message": "Unable to create item entries for collection : %s" % self.name})


class GetCollectionItemAssetURLsTest(TestCase):

    def setUp(self):
        """
        Setting up the required test data input for importer tasks test cases
        """
        self.name = 'branch-rickey-papers'
        self.item_id= 'mss37820001'

    @patch('importer.tasks.requests.get')  # Mock 'requests' module 'get' method.
    def test_get_collection_asset_urls(self, mock_get):
        """
        Testing no of collection item asset urls available in given item id
        """
        # Arrange
        collection = {"collection_name": self.name, "collection_slug": slugify(self.name), "collection_task_id": "123"}
        CollectionTaskDetails.objects.create(**collection)
        mock_resp = MockResponse(mock_data.COLLECTION_ITEM_URLS_DATA, 200)
        mock_get.return_value = mock_resp

        # Act
        response = get_collection_item_asset_urls(self.name, self.item_id)

        ctd = CollectionTaskDetails.objects.get(collection_slug=self.name)
        ciac = CollectionItemAssetCount.objects.get(collection_slug = ctd.collection_slug)

        # Assert
        self.assertEqual(ciac.collection_item_asset_count, 1)
        self.assertEqual(ciac.collection_item_identifier, self.item_id)
        self.assertEqual(ctd.collection_asset_count, 1)
        self.assertListEqual(response, ['http://tile.loc.gov/image-services/iiif/service:mss:mss37820:mss37820-052:08:0001/full/pct:100/0/default.jpg'])

    @patch('importer.tasks.requests.get')  # Mock 'requests' module 'get' method.
    def test_get_collection_asset_urls_no_db_entry(self, mock_get):
        """
        Testing no of collection item asset urls available in given item id wiht no db entry in CollectionTaskDetails
        """
        # Arrange
        mock_resp = MockResponse(mock_data.COLLECTION_ITEM_URLS_DATA, 200)
        mock_get.return_value = mock_resp

        # Act
        response = get_collection_item_asset_urls(self.name, self.item_id)

        # Assert
        self.assertListEqual(response, ['http://tile.loc.gov/image-services/iiif/service:mss:mss37820:mss37820-052:08:0001/full/pct:100/0/default.jpg'])