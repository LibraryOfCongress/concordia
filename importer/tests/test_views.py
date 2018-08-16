# TODO: Add correct copyright header

from unittest.mock import Mock, patch

from django.template.defaultfilters import slugify
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from importer.models import *


class CeleryMockResponse:
    """
    This class will be used by the mock to replace requests.get
    """

    def __init__(self, task_id):
        self.task_id = task_id


class MockAsyncResult:
    """
    This class will be used by the mock to replace requests.get
    """

    def __init__(self, state):
        self.state = state



class CreateCollectionViewTests(APITestCase):
    def setUp(self):
        """
        Setting up the required test data input for importer views test cases
        """
        self.client = APIClient()
        self.url = reverse("create_collection")
        self.data = {
            "name": "branch-rickey-papers",
            "url": "https://www.loc.gov/collections/branch-rickey-papers/?fa=partof:branch+rickey+papers:+baseball+file,+1906-1971",
            "project": "brp"
        }
        self.item_data = {
            "name": "branch-rickey-papers",
            "url": "https://www.loc.gov/item/mss859430021",
            "project": "brp"
        }
        self.collection = {
            "collection_name": self.data.get("name"),
            "collection_slug": slugify(self.data.get("name")),
            "subcollection_name": self.data.get("project"),
            "subcollection_slug": slugify(self.data.get("project")),
        }

    def test_create_collection_fields_required_bad_request(self):
        """
        Create collection with bad request, required fields not given project and url.
        """

        # Arrange
        data = {"name": "branch-rickey-papers1"}

        # Act
        response = self.client.post(self.url, data, format="json")

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_collection_wrong_url(self):
        """
        Create collection with bad request, in url collections or item or no present.
        """

        # Arrange
        data = {
            "name": "branch-rickey-papers",
            "url": "https://www.loc.gov/abc/mss859430021",
            "project": "brp"
        }

        # Act
        response = self.client.post(self.url, data, format="json")

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_collection_bad_request(self):
        """
        Create collection with bad request.
        """
        # Arrange
        self.collection["collection_task_id"] = "123"
        CollectionTaskDetails.objects.create(**self.collection)

        # Act
        response = self.client.post(self.url, self.data, format="json")

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("importer.views.download_write_collection_item_assets.delay")
    def test_create_collection(self, mock_download_func):
        """
        Create collection with proper data.
        """

        # Arrange
        mock_resp_instance = CeleryMockResponse("123")
        mock_download_func.return_value = mock_resp_instance

        # Act
        response = self.client.post(self.url, self.data, format="json")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data.get("task_id"), "123")

    @patch("importer.views.download_write_item_assets.delay")
    def test_create_item_with_db_entry(self, mock_download_func):
        """
        Create collection item with CollectionTaskDetails db entry.
        """
        # Arrange
        self.collection["collection_task_id"] = "123"
        CollectionTaskDetails.objects.create(**self.collection)
        mock_resp_instance = CeleryMockResponse("1234")
        mock_download_func.return_value = mock_resp_instance

        # Act
        response = self.client.post(self.url, self.item_data, format="json")

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data.get("task_id"), "1234")
        self.assertEqual(response.data.get("item_id"), "mss859430021")

    @patch("importer.views.download_write_item_assets.delay")
    def test_create_item_without_db_entry(self, mock_download_func):
        """
        Create collection item without CollectionTaskDetails db entry.
        """
        # Arrange
        mock_resp_instance = CeleryMockResponse("1234")
        mock_download_func.return_value = mock_resp_instance

        # Act
        response = self.client.post(self.url, self.item_data, format="json")

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data.get("task_id"), "1234")
        self.assertEqual(response.data.get("item_id"), "mss859430021")


