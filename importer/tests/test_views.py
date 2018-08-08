# TODO: Add correct copyright header

from unittest.mock import patch, Mock

from django.urls import reverse
from django.template.defaultfilters import slugify

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.test import APIClient

from importer.models import *


class CeleryMockResponse:
    """
    This class will be used by the mock to replace requests.get
    """

    def __init__(self, task_id):
        self.task_id = task_id



class CreateCollectionViewTests(APITestCase):

    def setUp(self):
        """
        Setting up the required test data input for importer views test cases
        """
        self.client = APIClient()
        self.url = reverse('create_collection')
        self.data = {
            'name': 'branch-rickey-papers',
            'url': 'https://www.loc.gov/collections/branch-rickey-papers/?fa=partof:branch+rickey+papers:+baseball+file,+1906-1971',
            'create_type': 'collections'
        }
        self.item_data = {
            'name': 'branch-rickey-papers',
            'url': 'https://www.loc.gov/item/mss859430021',
            'create_type': 'item'
        }
        self.collection = {"collection_name": self.data.get('name'),
                      "collection_slug": slugify(self.data.get('name'))}

    def test_create_collection_bad_request(self):
        """
        Create collection with bad request.
        """
        # Arrange
        self.collection[ "collection_task_id"] = "123"
        CollectionTaskDetails.objects.create(**self.collection)

        #Act
        response = self.client.post(self.url, self.data, format='json')

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data.get('message'),
                         "collection %s already exists"
                         % slugify(self.data.get('name')))

    @patch('importer.views.download_write_collection_item_assets.delay')
    def test_create_collection(self, mock_download_func):
        """
        Create collection with proper data.
        """

        # Arrange
        mock_resp_instance = CeleryMockResponse('123')
        mock_download_func.return_value = mock_resp_instance

        #Act
        response = self.client.post(self.url, self.data, format='json')

        # Assert
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data.get('task_id'), "123")

    @patch('importer.views.download_write_item_assets.delay')
    def test_create_item_with_db_entry(self, mock_download_func):
        """
        Create collection item with CollectionTaskDetails db entry.
        """
        # Arrange
        self.collection[ "collection_task_id"] = "123"
        CollectionTaskDetails.objects.create(**self.collection)
        mock_resp_instance = CeleryMockResponse('1234')
        mock_download_func.return_value = mock_resp_instance

        #Act
        response = self.client.post(self.url, self.item_data, format='json')

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data.get('task_id'), "1234")
        self.assertEqual(response.data.get('item_id'), "mss859430021")

    @patch('importer.views.download_write_item_assets.delay')
    def test_create_item_without_db_entry(self, mock_download_func):
        """
        Create collection item without CollectionTaskDetails db entry.
        """
        # Arrange
        mock_resp_instance = CeleryMockResponse('1234')
        mock_download_func.return_value = mock_resp_instance

        #Act
        response = self.client.post(self.url, self.item_data, format='json')

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data.get('task_id'), "1234")
        self.assertEqual(response.data.get('item_id'), "mss859430021")