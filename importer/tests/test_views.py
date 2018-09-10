# TODO: Add correct copyright header

from unittest.mock import Mock, patch

from django.conf import settings
from django.template.defaultfilters import slugify
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from importer.models import *
from importer.views import *


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


class CreateCampaignViewTests(APITestCase):
    def setUp(self):
        """
        Setting up the required test data input for importer views test cases
        """
        self.client = APIClient()
        self.url = reverse("create_campaign")
        self.data = {
            "name": "branch-rickey-papers",
            "url": "https://www.loc.gov/collections/branch-rickey-papers/?fa=partof:branch+rickey+papers:+baseball+file,+1906-1971",
            "project": "brp",
        }
        self.item_data = {
            "name": "branch-rickey-papers",
            "url": "https://www.loc.gov/item/mss859430021",
            "project": "brp",
        }
        self.campaign = {
            "campaign_name": self.data.get("name"),
            "campaign_slug": slugify(self.data.get("name")),
            "project_name": self.data.get("project"),
            "project_slug": slugify(self.data.get("project")),
        }

    def test_create_campaign_fields_required_bad_request(self):
        """
        Create campaign with bad request, required fields not given project and url.
        """

        # Arrange
        data = {"name": "branch-rickey-papers1"}

        # Act
        response = self.client.post(self.url, data, format="json")

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_campaign_wrong_url(self):
        """
        Create campaign with bad request, in url campaigns or item or no present.
        """

        # Arrange
        data = {
            "name": "branch-rickey-papers",
            "url": "https://www.loc.gov/abc/mss859430021",
            "project": "brp",
        }

        # Act
        response = self.client.post(self.url, data, format="json")

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_campaign_bad_request(self):
        """
        Create campaign with bad request.
        """
        # Arrange
        self.campaign["campaign_task_id"] = "123"
        CampaignTaskDetails.objects.create(**self.campaign)

        # Act
        response = self.client.post(self.url, self.data, format="json")

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("importer.views.download_write_campaign_item_assets.delay")
    def test_create_campaign(self, mock_download_func):
        """
        Create campaign with proper data.
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
        Create campaign item with CampaignTaskDetails db entry.
        """
        # Arrange
        self.campaign["campaign_task_id"] = "123"
        CampaignTaskDetails.objects.create(**self.campaign)
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
        Create campaign item without CampaignTaskDetails db entry.
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


class GetTaskStatusTests(APITestCase):
    def setUp(self):
        """
        Setting up the required test data input for importer views test cases
        """
        self.client = APIClient()
        self.url = reverse("get_task_status", kwargs={"task_id": "123abc"})
        self.data = {
            "name": "branch-rickey-papers",
            "url": "https://www.loc.gov/collections/branch-rickey-papers/?fa=partof:branch+rickey+papers:+baseball+file,+1906-1971",
            "project": "brp",
        }
        self.item_data = {
            "name": "branch-rickey-papers",
            "url": "https://www.loc.gov/item/mss859430021",
            "project": "brp",
        }
        self.campaign = {
            "campaign_name": self.data.get("name"),
            "campaign_slug": slugify(self.data.get("name")),
            "project_name": self.data.get("project"),
            "project_slug": slugify(self.data.get("project")),
        }

    @patch("importer.views.AsyncResult")
    def test_get_task_status_with_no_campaign(self, mock_async):
        """
        Get task status of not existed campaign
        """

        # Arrange
        async_obj = MockAsyncResult("PENDING")
        mock_async.return_value = async_obj

        # Act
        response = self.client.get(self.url, format="json")

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEquals(
            response.data.get("message"),
            "Requested task id Does not exists campaign progress",
        )

    @patch("importer.views.sum")
    @patch("importer.views.AsyncResult")
    def test_get_task_status_no_asset(self, mock_async, mock_sum):
        """
        get task status of not existed campaign assets db entry
        """
        # Arrange
        async_obj = MockAsyncResult("INPROGRESS")
        mock_async.return_value = async_obj
        self.campaign["campaign_task_id"] = "123abc"
        self.campaign["campaign_asset_count"] = 5
        mock_sum.return_value = 3
        CampaignTaskDetails.objects.create(**self.campaign)

        # Act
        response = self.client.get(self.url, format="json")

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEquals(response.data.get("state"), "INPROGRESS")
        self.assertEquals(response.data.get("progress"), "3 of 5 processed")

        # Arrange
        async_obj = MockAsyncResult("SUCCESS")
        mock_async.return_value = async_obj
        mock_sum.return_value = 5

        # Act
        response = self.client.get(self.url, format="json")

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEquals(response.data.get("state"), "SUCCESS")
        self.assertEquals(response.data.get("progress"), "5 of 5 processed")

    @patch("importer.views.sum")
    @patch("importer.views.AsyncResult")
    def test_get_task_status_with_asset(self, mock_async, mock_sum):
        """
        get task status of existed campaign assets db entry
        """
        # Arrange
        async_obj = MockAsyncResult("INPROGRESS")
        mock_async.return_value = async_obj
        mock_sum.return_value = 3
        ctd = CampaignTaskDetails.objects.create(**self.campaign)
        CampaignItemAssetCount.objects.create(
            campaign_task=ctd,
            campaign_item_identifier="abc",
            campaign_item_asset_count=5,
            item_task_id="123abc",
        )

        # Act
        response = self.client.get(self.url, format="json")

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEquals(response.data.get("state"), "INPROGRESS")
        self.assertEquals(response.data.get("progress"), "3 of 5 processed")


class CheckAndSaveCampaignAssetsTests(APITestCase):
    def setUp(self):
        """
        Setting up the required test data input for importer views test cases
        """
        self.client = APIClient()
        self.url_itemid = reverse(
            "check_and_save_campaign_item_assets",
            kwargs={"task_id": "123abc", "item_id": "123abc"},
        )
        self.url = reverse(
            "check_and_save_campaign_assets", kwargs={"task_id": "123abc"}
        )
        self.data = {
            "name": "branch-rickey-papers",
            "url": "https://www.loc.gov/collections/branch-rickey-papers/?fa=partof:branch+rickey+papers:+baseball+file,+1906-1971",
            "project": "brp",
        }
        self.item_data = {
            "name": "branch-rickey-papers",
            "url": "https://www.loc.gov/item/mss859430021",
            "project": "brp",
        }
        self.campaign = {
            "campaign_name": self.data.get("name"),
            "campaign_slug": slugify(self.data.get("name")),
            "project_name": self.data.get("project"),
            "project_slug": slugify(self.data.get("project")),
        }

    def test_campaign_assets_fail_no_db_entry(self):
        """
        no CampaignItemAssetCount db entry
        """

        # Arrange

        # Act
        response = self.client.get(self.url_itemid)

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data.get("message"), "Requested Campaign Does not exists"
        )

    def test_campaign_assets_fail_no_itemid(self):
        """
        no CampaignAssetCount db entry without itemid
        """

        # Arrange

        # Act
        response = self.client.get(self.url)

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data.get("message"), "Requested Campaign Does not exists"
        )

    @patch("importer.views.check_and_save_item_completeness")
    def test_campaign_assets_with_db_entry(self, mock_complete):
        """
        check and save CampaignItemAssetCount with db entry
        """

        # Arrange
        mock_complete.return_value = True
        ctd = CampaignTaskDetails.objects.create(**self.campaign)
        CampaignItemAssetCount.objects.create(
            campaign_task=ctd,
            campaign_item_identifier="123abc",
            campaign_item_asset_count=5,
            item_task_id="123abc",
        )

        # Act
        response = self.client.get(self.url_itemid)
        # Assert that the request-response cycle completed successfully.
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)

    @patch("importer.views.check_and_save_campaign_completeness")
    def test_campaign_assets_with_db_no_itemid(self, mock_complete):
        """
        check and save CampaignAssetCount db entry without itemid
        """

        # Arrange
        mock_complete.return_value = True
        self.campaign["campaign_task_id"] = "123abc"
        ctd = CampaignTaskDetails.objects.create(**self.campaign)
        CampaignItemAssetCount.objects.create(
            campaign_task=ctd,
            campaign_item_identifier="123abc",
            campaign_item_asset_count=5,
            item_task_id="123abc",
        )

        # Act
        response = self.client.get(self.url)

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)

    @patch("importer.views.check_and_save_item_completeness")
    def test_campaign_assets_with_db_entry_not_complete(self, mock_complete):
        """
        check and save CampaignItemAssetCount with db entry not completeness
        """

        # Arrange
        mock_complete.return_value = False
        ctd = CampaignTaskDetails.objects.create(**self.campaign)
        CampaignItemAssetCount.objects.create(
            campaign_task=ctd,
            campaign_item_identifier="123abc",
            campaign_item_asset_count=5,
            item_task_id="123abc",
        )

        # Act
        response = self.client.get(self.url_itemid)
        # Assert that the request-response cycle completed successfully.
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data.get("message"),
            "Creating a campaign is failed since assets are not completely downloaded",
        )

    @patch("importer.views.check_and_save_campaign_completeness")
    def test_campaign_assets_with_db_no_itemid_not_complete(self, mock_complete):
        """
        check and save CampaignAssetCount db entry without itemid not completeness
        """

        # Arrange
        mock_complete.return_value = False
        self.campaign["campaign_task_id"] = "123abc"
        ctd = CampaignTaskDetails.objects.create(**self.campaign)
        CampaignItemAssetCount.objects.create(
            campaign_task=ctd,
            campaign_item_identifier="123abc",
            campaign_item_asset_count=5,
            item_task_id="123abc",
        )

        # Act
        response = self.client.get(self.url)

        # Assert that the request-response cycle completed successfully.
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data.get("message"),
            "Creating a campaign is failed since assets are not completely downloaded",
        )

    def test_check_and_save_campaign_completeness(self):
        """
        Test check_and_save_campaign_completeness
        :return:
        """

        # Arrange

        campaign_task_detail = CampaignTaskDetails(
            campaign_name="campaign name",
            campaign_slug="campaign_slug",
            project_name="project name",
            project_slug="project_slug",
            campaign_item_count=1,
            campaign_asset_count=1,
            campaign_task_id="task_id",
        )

        campaign_task_detail.save()

        campaign_item_asset_count = CampaignItemAssetCount(
            item_task_id="task_id",
            campaign_task=campaign_task_detail,
            campaign_item_identifier="campaign_item_identifer",
            campaign_item_asset_count=1,
        )
        campaign_item_asset_count.save()

        test_dir = "/tmp/concordia_images/campaign_slug/project_slug/"
        if not os.path.exists(test_dir):
            os.makedirs(test_dir)

        # add a file to test_dir
        with open(test_dir + "1", "a") as the_file:
            the_file.write("Hello\n")

        # Act
        result = check_and_save_campaign_completeness(campaign_item_asset_count)
        # shutil.rmtree(settings.MEDIA_ROOT) #if media folder wants to delete in test cases

        # Assert
        self.assertEqual(result, True)

    def test_check_and_save_campaign_completeness_false(self):
        """
        Test check_and_save_campaign_completeness_false
        :return:
        """

        # Arrange

        campaign_task_detail = CampaignTaskDetails(
            campaign_name="campaign name",
            campaign_slug="campaign_slug",
            project_name="project name",
            project_slug="project_slug",
            campaign_item_count=1,
            campaign_asset_count=2,
            campaign_task_id="task_id",
        )

        campaign_task_detail.save()

        campaign_item_asset_count = CampaignItemAssetCount(
            item_task_id="task_id",
            campaign_task=campaign_task_detail,
            campaign_item_identifier="campaign_item_identifer",
        )
        campaign_item_asset_count.save()

        test_dir = "/tmp/concordia_images/campaign_slug/project_slug/"
        if not os.path.exists(test_dir):
            os.makedirs(test_dir)

        # add a file to test_dir
        with open(test_dir + "1", "a") as the_file:
            the_file.write("Hello\n")

        # Act
        result = check_and_save_campaign_completeness(campaign_item_asset_count)

        # Assert
        self.assertEqual(result, False)

    def test_check_and_saveitem_completeness(self):
        """
        Test check_and_save_item_completeness
        :return:
        """

        # Arrange

        campaign_task_detail = CampaignTaskDetails(
            campaign_name="campaign name",
            campaign_slug="campaign_slug",
            project_name="project name",
            project_slug="project_slug",
        )

        campaign_task_detail.save()

        campaign_item_asset_count = CampaignItemAssetCount(
            item_task_id="task_id",
            campaign_task=campaign_task_detail,
            campaign_item_identifier="campaign_item_identifer",
            campaign_item_asset_count=1,
        )
        campaign_item_asset_count.save()

        test_dir = (
            "/tmp/concordia_images/campaign_slug/project_slug/campaign_item_identifer/"
        )
        if not os.path.exists(test_dir):
            os.makedirs(test_dir)

        # add a file to test_dir
        with open(test_dir + "1", "a") as the_file:
            the_file.write("Hello\n")

        # Act
        result = check_and_save_item_completeness(
            campaign_item_asset_count, "campaign_item_identifer"
        )
        # shutil.rmtree(settings.MEDIA_ROOT) #if media folder wants to delete in test cases

        # Assert
        self.assertEqual(result, True)

    def test_check_and_saveitem_completeness_not_proper_write(self):
        """
        Test test_check_and_saveitem_completeness_not_proper_write
        :return:
        """

        # Arrange

        campaign_task_detail = CampaignTaskDetails(
            campaign_name="campaign name",
            campaign_slug="campaign_slug",
            project_name="project name",
            project_slug="project_slug",
        )

        campaign_task_detail.save()

        campaign_item_asset_count = CampaignItemAssetCount(
            item_task_id="task_id",
            campaign_task=campaign_task_detail,
            campaign_item_identifier="campaign_item_identifer",
            campaign_item_asset_count=2,
        )
        campaign_item_asset_count.save()

        test_dir = (
            "/tmp/concordia_images/campaign_slug/project_slug/campaign_item_identifer/"
        )
        if not os.path.exists(test_dir):
            os.makedirs(test_dir)

        # add a file to test_dir
        with open(test_dir + "1", "a") as the_file:
            the_file.write("Hello\n")

        # Act
        result = check_and_save_item_completeness(
            campaign_item_asset_count, "campaign_item_identifer"
        )

        # Assert
        self.assertEqual(result, False)
