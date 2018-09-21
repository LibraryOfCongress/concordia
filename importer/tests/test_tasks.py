# TODO: Add correct copyright header

import io
from unittest.mock import mock_open, patch

from django.test import TestCase
from django.template.defaultfilters import slugify

from importer.models import CampaignItemAssetCount, CampaignTaskDetails
from importer.tasks import (
    download_write_campaign_item_asset,
    get_item_id_from_item_url,
    get_campaign_pages,
    get_collection_item_ids,
    get_campaign_item_asset_urls,
    download_write_campaign_item_assets,
    download_write_item_assets,
)
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


class GetCampaignPagesTest(TestCase):
    def setUp(self):
        """
        Setting up the required test data input for importer tasks test cases
        """
        self.url = "https://www.loc.gov/collections/branch-rickey-papers/?fa=partof:branch+rickey+papers:+baseball+file,+1906-1971"

    @patch("importer.tasks.requests.get")  # Mock 'requests' module 'get' method.
    def test_get_campaign_pages(self, mock_get):
        """
        get campaign pages successfully with pages info
        """
        # Arrange
        # Construct our mock response object, giving it relevant expected behaviours
        mock_resp_instance = MockResponse({"pagination": {"total": 10}}, 200)
        mock_get.return_value = mock_resp_instance

        # Act
        response = get_campaign_pages(self.url)

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(mock_resp_instance.status_code, 200)
        self.assertEqual(response, 10)

    @patch("importer.tasks.requests.get")  # Mock 'requests' module 'get' method.
    def test_get_campaign_sucess_no_pages(self, mock_get):
        """
        get campaign pages successfully with no pages info
        """

        # Arrange
        # Construct our mock response object, giving it relevant expected behaviours
        mock_resp_instance = MockResponse({}, 200)
        mock_get.return_value = mock_resp_instance

        # Act
        response = get_campaign_pages(self.url)

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(mock_resp_instance.status_code, 200)
        self.assertEqual(response, 0)


class GetCampaignItemidsTest(TestCase):
    def setUp(self):
        """
        Setting up the required test data input for importer tasks test cases
        """
        self.url = "https://www.loc.gov/collections/branch-rickey-papers/?fa=partof:branch+rickey+papers:+baseball+file,+1906-1971"

    @patch("importer.tasks.requests.get")  # Mock 'requests' module 'get' method.
    def test_get_campaign_item_ids(self, mock_get):
        """
        Testing no of campaign item ids available in given campaign url
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
    def test_get_campaign_item_ids_no_ids(self, mock_get):
        """
        Testing no of campaign item ids not availabel campaign url
        """
        # Arrange
        mock_page1_result = MockResponse({}, 200)
        mock_page2_result = MockResponse({}, 200)
        mock_get.side_effect = [mock_page1_result, mock_page2_result]

        # Act
        response = get_collection_item_ids(self.url, 2)

        # Arrange
        self.assertListEqual(response, [])


class GetCampaignItemAssetURLsTest(TestCase):
    def setUp(self):
        """
        Setting up the required test data input for importer tasks test cases
        """
        self.item_id = "mss37820001"

    @patch("importer.tasks.requests.get")  # Mock 'requests' module 'get' method.
    def test_get_campaign_asset_urls(self, mock_get):
        """
        Testing no of campaign item asset urls available in given item id
        """
        # Arrange
        mock_resp = MockResponse(mock_data.COLLECTION_ITEM_URLS_DATA, 200)
        mock_get.return_value = mock_resp

        # Act
        response = get_campaign_item_asset_urls(self.item_id)

        # Assert
        self.assertListEqual(
            response,
            [
                "http://tile.loc.gov/image-services/iiif/service:mss:mss37820:mss37820-052:08:0001/full/pct:100/0/default.jpg"
            ],
        )

    @patch("importer.tasks.requests.get")  # Mock 'requests' module 'get' method.
    def test_get_campaign_no_asset_urls(self, mock_get):
        """
        Testing no of campaign item asset urls not available in given item id
        """
        # Arrange
        mock_resp = MockResponse({}, 200)
        mock_get.return_value = mock_resp

        # Act
        response = get_campaign_item_asset_urls(self.item_id)

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
            try:
                download_write_campaign_item_asset("dumy/image/url", "foo")
            except Exception as exc:
                self.fail(
                    "Expected download_write_campaign_item_asset to complete normally but caught %s"
                    % exc
                )

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
            abc = download_write_campaign_item_asset("dumy/image/url", "foo")

            # Assert
            self.assertEquals(abc, False)


class DownloadWriteCampaignItemAssetsTest(TestCase):
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
    def test_download_write_campaign_item_asstes(self, mock_get, mock_save):
        """
        Testing no of campaign item asset urls available in given campaign url
        """
        # Arrange

        campaign = {
            "campaign_name": self.name,
            "campaign_slug": slugify(self.name),
            "campaign_task_id": "123",
            "project_name": self.project,
            "project_slug": slugify(self.project),
        }
        CampaignTaskDetails.objects.create(**campaign)

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
        download_write_campaign_item_assets(self.name, self.project, self.url)

        ctd = CampaignTaskDetails.objects.get(
            campaign_slug=self.name, project_slug=self.project
        )
        ciac = CampaignItemAssetCount.objects.get(campaign_task=ctd)

        # Assert
        self.assertEqual(ciac.campaign_item_asset_count, 1)
        self.assertEqual(ciac.campaign_item_identifier, self.item_id)
        self.assertEqual(ctd.campaign_asset_count, 1)

    @patch("importer.tasks.get_save_item_assets")
    @patch("importer.tasks.requests.get")  # Mock 'requests' module 'get' method.
    def test_download_write_campaign_item_asstes_no_db_entry(self, mock_get, mock_save):
        """
        Testing no of campaign item asset urls available in given campaign url wiht no db entry in CampaignTaskDetails
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
        download_write_campaign_item_assets(self.name, self.project, self.url)

        ctd = CampaignTaskDetails.objects.get(
            campaign_slug=self.name, project_slug=self.project
        )
        ciac = CampaignItemAssetCount.objects.get(
            campaign_task=ctd, campaign_item_identifier=self.item_id
        )

        # Assert
        self.assertEqual(ciac.campaign_item_asset_count, 1)
        self.assertEqual(ciac.campaign_item_identifier, self.item_id)
        self.assertEqual(ctd.campaign_asset_count, 1)


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
        Testing no of campaign item asset urls available in given item id
        """
        # Arrange

        campaign = {
            "campaign_name": self.name,
            "campaign_slug": slugify(self.name),
            "campaign_task_id": "123",
            "project_name": self.project,
            "project_slug": slugify(self.project),
        }
        CampaignTaskDetails.objects.create(**campaign)
        mock_resp = MockResponse(mock_data.COLLECTION_ITEM_URLS_DATA, 200)
        mock_get.return_value = mock_resp
        mock_save.return_value = None

        # Act
        download_write_item_assets(self.name, self.project, self.item_id)

        ctd = CampaignTaskDetails.objects.get(
            campaign_slug=self.name, project_slug=self.project
        )
        ciac = CampaignItemAssetCount.objects.get(
            campaign_task=ctd, campaign_item_identifier=self.item_id
        )

        # Assert
        self.assertEqual(ciac.campaign_item_asset_count, 1)
        self.assertEqual(ciac.campaign_item_identifier, self.item_id)
        self.assertEqual(ctd.campaign_asset_count, 1)

    @patch("importer.tasks.get_save_item_assets")
    @patch("importer.tasks.requests.get")  # Mock 'requests' module 'get' method.
    def test_download_write_item_asstes_no_db_entry(self, mock_get, mock_save):
        """
        Testing no of campaign item asset urls available in given item id wiht no db entry in CampaignTaskDetails
        """
        # Arrange
        mock_resp = MockResponse(mock_data.COLLECTION_ITEM_URLS_DATA, 200)
        mock_get.return_value = mock_resp
        mock_save.return_value = None

        # Act
        download_write_item_assets(self.name, self.project, self.item_id)

        ctd = CampaignTaskDetails.objects.get(
            campaign_slug=self.name, project_slug=self.project
        )
        ciac = CampaignItemAssetCount.objects.get(
            campaign_task=ctd, campaign_item_identifier=self.item_id
        )

        # Assert
        self.assertEqual(ciac.campaign_item_asset_count, 1)
        self.assertEqual(ciac.campaign_item_identifier, self.item_id)
        self.assertEqual(ctd.campaign_asset_count, 1)
