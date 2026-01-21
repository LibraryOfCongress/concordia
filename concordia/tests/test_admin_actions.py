import uuid
from unittest import mock

from django.contrib.auth.models import User
from django.http import HttpRequest
from django.test import TestCase

from concordia.admin.actions import (
    anonymize_action,
    change_status_to_completed,
    change_status_to_in_progress,
    change_status_to_needs_review,
    publish_action,
    publish_item_action,
    unpublish_action,
    unpublish_item_action,
    verify_assets_action,
)
from concordia.models import (
    Asset,
    Campaign,
    Item,
    Project,
    TranscriptionStatus,
)
from concordia.tests.utils import (
    CreateTestUsers,
    create_asset,
    create_campaign,
    create_item,
    create_project,
    create_transcription,
)
from concordia.utils import get_anonymous_user


class MockModelAdmin:
    pass


request = HttpRequest()
modeladmin = MockModelAdmin()


class UserAdminActionTest(TestCase, CreateTestUsers):
    def setUp(self):
        self.user1 = self.create_user("user1")
        self.user2 = self.create_user("user2")
        self.user3 = self.create_user("user3")

    def test_anonymize_action(self):
        queryset = User.objects.filter(pk__in=(self.user1.pk, self.user3.pk))
        anonymize_action(modeladmin, request, queryset)
        user1 = User.objects.get(pk=self.user1.pk)
        user2 = User.objects.get(pk=self.user2.pk)
        user3 = User.objects.get(pk=self.user3.pk)

        self.assertIn("Anonymized", user1.username)
        self.assertEqual(self.user2.username, user2.username)
        self.assertIn("Anonymized", user3.username)

        self.assertEqual("", user1.email)
        self.assertEqual(self.user2.email, user2.email)
        self.assertEqual("", user3.email)

        self.assertFalse(user1.has_usable_password())
        self.assertTrue(user2.has_usable_password())
        self.assertFalse(user3.has_usable_password())

        self.assertFalse(user1.check_password(self.user1._password))
        self.assertTrue(user2.check_password(self.user2._password))
        self.assertFalse(user3.check_password(self.user3._password))

        self.assertFalse(user1.is_active)
        self.assertTrue(user2.is_active)
        self.assertFalse(user3.is_active)


class ItemAdminActionTest(TestCase):
    def _setUp(self, published=True):
        self.asset1 = create_asset(published=published)
        self.item1 = self.asset1.item
        self.project = self.item1.project

        self.item2 = create_item(project=self.project, item_id="2", published=published)
        self.asset2 = create_asset(
            item=self.item2, slug="test-asset-slug-2", published=published
        )

        self.item3 = create_item(project=self.project, item_id="3", published=published)
        self.asset3 = create_asset(
            item=self.item3, slug="test-asset-slug-3", published=published
        )
        self.asset4 = create_asset(
            item=self.item3, slug="test-asset-slug-4", published=published
        )

    def test_publish_item_action(self):
        self._setUp(False)
        queryset = Item.objects.filter(pk__in=[self.item1.pk, self.item3.pk])
        publish_item_action(modeladmin, request, queryset)
        item1 = Item.objects.get(pk=self.item1.pk)
        asset1 = Asset.objects.get(pk=self.asset1.pk)
        item2 = Item.objects.get(pk=self.item2.pk)
        asset2 = Asset.objects.get(pk=self.asset2.pk)
        item3 = Item.objects.get(pk=self.item3.pk)
        asset3 = Asset.objects.get(pk=self.asset3.pk)
        asset4 = Asset.objects.get(pk=self.asset4.pk)

        self.assertTrue(item1.published)
        self.assertTrue(asset1.published)
        self.assertFalse(item2.published)
        self.assertFalse(asset2.published)
        self.assertTrue(item3.published)
        self.assertTrue(asset3.published)
        self.assertTrue(asset4.published)

    def test_unpublish_item_action(self):
        self._setUp(True)
        queryset = Item.objects.filter(pk__in=[self.item1.pk, self.item3.pk])
        unpublish_item_action(modeladmin, request, queryset)
        item1 = Item.objects.get(pk=self.item1.pk)
        asset1 = Asset.objects.get(pk=self.asset1.pk)
        item2 = Item.objects.get(pk=self.item2.pk)
        asset2 = Asset.objects.get(pk=self.asset2.pk)
        item3 = Item.objects.get(pk=self.item3.pk)
        asset3 = Asset.objects.get(pk=self.asset3.pk)
        asset4 = Asset.objects.get(pk=self.asset4.pk)

        self.assertFalse(item1.published)
        self.assertFalse(asset1.published)
        self.assertTrue(item2.published)
        self.assertTrue(asset2.published)
        self.assertFalse(item3.published)
        self.assertFalse(asset3.published)
        self.assertFalse(asset4.published)


class AssetAdminActionTest(TestCase, CreateTestUsers):
    def setUp(self):
        self.user = self.create_user("testuser")
        self.reviewed_asset = create_asset()
        self.unreviewed_asset = create_asset(
            item=self.reviewed_asset.item, slug="unreviewed-asset"
        )
        self.untranscribed_asset = create_asset(
            item=self.reviewed_asset.item, slug="untranscribed-asset"
        )
        self.asset_pks = [
            self.reviewed_asset.pk,
            self.unreviewed_asset.pk,
            self.untranscribed_asset.pk,
        ]
        self.anon_user = get_anonymous_user()
        self.request = HttpRequest()
        self.request.user = self.user
        create_transcription(asset=self.reviewed_asset, user=self.anon_user)
        create_transcription(asset=self.unreviewed_asset, user=self.anon_user)
        create_transcription(
            asset=self.reviewed_asset,
            user=self.anon_user,
            reviewed_by=self.user,
        )

    def test_change_status_to_completed(self):
        queryset = Asset.objects.filter(pk__in=self.asset_pks)
        change_status_to_completed(modeladmin, self.request, queryset)

        reviewed_asset = Asset.objects.get(pk=self.reviewed_asset.pk)
        unreviewed_asset = Asset.objects.get(pk=self.unreviewed_asset.pk)
        untranscribed_asset = Asset.objects.get(pk=self.untranscribed_asset.pk)

        self.assertEqual(
            reviewed_asset.transcription_status, TranscriptionStatus.COMPLETED
        )
        self.assertEqual(
            unreviewed_asset.transcription_status, TranscriptionStatus.COMPLETED
        )
        self.assertEqual(
            untranscribed_asset.transcription_status, TranscriptionStatus.COMPLETED
        )

    def test_change_status_to_needs_review(self):
        queryset = Asset.objects.filter(pk__in=self.asset_pks)
        change_status_to_needs_review(modeladmin, self.request, queryset)

        reviewed_asset = Asset.objects.get(pk=self.reviewed_asset.pk)
        unreviewed_asset = Asset.objects.get(pk=self.unreviewed_asset.pk)
        untranscribed_asset = Asset.objects.get(pk=self.untranscribed_asset.pk)

        self.assertEqual(
            reviewed_asset.transcription_status, TranscriptionStatus.SUBMITTED
        )
        self.assertEqual(
            unreviewed_asset.transcription_status, TranscriptionStatus.SUBMITTED
        )
        self.assertEqual(
            untranscribed_asset.transcription_status, TranscriptionStatus.SUBMITTED
        )

    def test_change_status_to_in_progress(self):
        queryset = Asset.objects.filter(pk__in=self.asset_pks)
        change_status_to_in_progress(modeladmin, self.request, queryset)

        reviewed_asset = Asset.objects.get(pk=self.reviewed_asset.pk)
        unreviewed_asset = Asset.objects.get(pk=self.unreviewed_asset.pk)
        untranscribed_asset = Asset.objects.get(pk=self.untranscribed_asset.pk)

        self.assertEqual(
            reviewed_asset.transcription_status, TranscriptionStatus.IN_PROGRESS
        )
        self.assertEqual(
            unreviewed_asset.transcription_status, TranscriptionStatus.IN_PROGRESS
        )
        self.assertEqual(
            untranscribed_asset.transcription_status, TranscriptionStatus.IN_PROGRESS
        )

    def test_change_status_to_completed_message_single(self):
        queryset = Asset.objects.filter(pk__in=[self.untranscribed_asset.pk])
        with mock.patch("concordia.admin.actions.messages.info") as mock_info:
            change_status_to_completed(modeladmin, self.request, queryset)

        self.assertTrue(mock_info.called)
        args, kwargs = mock_info.call_args
        self.assertIs(args[0], self.request)
        self.assertIn("Changed status of", args[1])
        self.assertIn(self.untranscribed_asset.title, args[1])
        self.assertIn("to Complete", args[1])

    def test_change_status_to_completed_message_multiple(self):
        queryset = Asset.objects.filter(
            pk__in=[self.unreviewed_asset.pk, self.untranscribed_asset.pk]
        )
        with mock.patch("concordia.admin.actions.messages.info") as mock_info:
            change_status_to_completed(modeladmin, self.request, queryset)

        self.assertTrue(mock_info.called)
        args, kwargs = mock_info.call_args
        self.assertIs(args[0], self.request)
        self.assertIn("Changed status of 2 assets to Complete", args[1])

    def test_change_status_to_needs_review_message_single(self):
        queryset = Asset.objects.filter(pk__in=[self.untranscribed_asset.pk])
        with mock.patch("concordia.admin.actions.messages.info") as mock_info:
            change_status_to_needs_review(modeladmin, self.request, queryset)

        self.assertTrue(mock_info.called)
        args, kwargs = mock_info.call_args
        self.assertIs(args[0], self.request)
        self.assertIn("Changed status of", args[1])
        self.assertIn(self.untranscribed_asset.title, args[1])
        self.assertIn("to Needs Review", args[1])

    def test_change_status_to_in_progress_message_multiple(self):
        extra_asset = create_asset(
            item=self.reviewed_asset.item, slug="extra-no-tx-for-in-progress"
        )

        queryset = Asset.objects.filter(
            pk__in=[self.untranscribed_asset.pk, extra_asset.pk]
        )

        with mock.patch("concordia.admin.actions.messages.info") as mock_info:
            change_status_to_in_progress(modeladmin, self.request, queryset)

        self.assertTrue(mock_info.called)
        args, kwargs = mock_info.call_args
        self.assertIs(args[0], self.request)
        self.assertIn("Changed status of 2 assets to In Progress", args[1])


class AdminActionTest(TestCase):
    def _setUp(self, published=True):
        self.asset1 = create_asset(published=published)
        self.item1 = self.asset1.item
        self.project1 = self.item1.project
        self.campaign1 = self.project1.campaign

        self.campaign2 = create_campaign(
            slug="test-campaign-slug-2", published=published
        )
        self.project2 = create_project(
            campaign=self.campaign2, slug="test-project-slug-2", published=published
        )
        self.item2 = create_item(
            project=self.project2, item_id="2", published=published
        )
        self.asset2 = create_asset(
            item=self.item2, slug="test-asset-slug-2", published=published
        )

        self.campaign3 = create_campaign(
            slug="test-campaign-slug-3", published=published
        )
        self.project3 = create_project(
            campaign=self.campaign3, slug="test-project-slug-3", published=published
        )
        self.item3 = create_item(
            project=self.project3, item_id="3", published=published
        )
        self.asset3 = create_asset(
            item=self.item3, slug="test-asset-slug-3", published=published
        )
        self.asset4 = create_asset(
            item=self.item3, slug="test-asset-slug-4", published=published
        )

    def test_publish_action(self):
        self._setUp(False)
        queryset = Campaign.objects.filter(
            pk__in=[self.campaign1.pk, self.campaign3.pk]
        )
        publish_action(modeladmin, request, queryset)
        campaign1 = Campaign.objects.get(pk=self.campaign1.pk)
        campaign2 = Campaign.objects.get(pk=self.campaign2.pk)
        campaign3 = Campaign.objects.get(pk=self.campaign3.pk)
        project1 = Project.objects.get(pk=self.project1.pk)

        self.assertTrue(campaign1.published)
        self.assertFalse(campaign2.published)
        self.assertTrue(campaign3.published)
        self.assertFalse(project1.published)

        queryset = Project.objects.filter(pk__in=[self.project2.pk])
        publish_action(modeladmin, request, queryset)
        project1 = Project.objects.get(pk=self.project1.pk)
        project2 = Project.objects.get(pk=self.project2.pk)
        project3 = Project.objects.get(pk=self.project3.pk)
        item2 = Item.objects.get(pk=self.item2.pk)

        self.assertFalse(project1.published)
        self.assertTrue(project2.published)
        self.assertFalse(project3.published)
        self.assertFalse(item2.published)

        queryset = Asset.objects.filter(
            pk__in=[self.asset1.pk, self.asset2.pk, self.asset3.pk]
        )
        publish_action(modeladmin, request, queryset)
        asset1 = Asset.objects.get(pk=self.asset1.pk)
        asset2 = Asset.objects.get(pk=self.asset2.pk)
        asset3 = Asset.objects.get(pk=self.asset3.pk)
        asset4 = Asset.objects.get(pk=self.asset4.pk)

        self.assertTrue(asset1.published)
        self.assertTrue(asset2.published)
        self.assertTrue(asset3.published)
        self.assertFalse(asset4.published)

    def test_unpublish_action(self):
        self._setUp(True)
        queryset = Campaign.objects.filter(
            pk__in=[self.campaign1.pk, self.campaign3.pk]
        )
        unpublish_action(modeladmin, request, queryset)
        campaign1 = Campaign.objects.get(pk=self.campaign1.pk)
        campaign2 = Campaign.objects.get(pk=self.campaign2.pk)
        campaign3 = Campaign.objects.get(pk=self.campaign3.pk)
        project1 = Project.objects.get(pk=self.project1.pk)

        self.assertFalse(campaign1.published)
        self.assertTrue(campaign2.published)
        self.assertFalse(campaign3.published)
        self.assertTrue(project1.published)

        queryset = Project.objects.filter(pk__in=[self.project2.pk])
        unpublish_action(modeladmin, request, queryset)
        project1 = Project.objects.get(pk=self.project1.pk)
        project2 = Project.objects.get(pk=self.project2.pk)
        project3 = Project.objects.get(pk=self.project3.pk)
        item2 = Item.objects.get(pk=self.item2.pk)

        self.assertTrue(project1.published)
        self.assertFalse(project2.published)
        self.assertTrue(project3.published)
        self.assertTrue(item2.published)

        queryset = Asset.objects.filter(
            pk__in=[self.asset1.pk, self.asset2.pk, self.asset3.pk]
        )
        unpublish_action(modeladmin, request, queryset)
        asset1 = Asset.objects.get(pk=self.asset1.pk)
        asset2 = Asset.objects.get(pk=self.asset2.pk)
        asset3 = Asset.objects.get(pk=self.asset3.pk)
        asset4 = Asset.objects.get(pk=self.asset4.pk)

        self.assertFalse(asset1.published)
        self.assertFalse(asset2.published)
        self.assertFalse(asset3.published)
        self.assertTrue(asset4.published)


class VerifyAssetsActionTest(TestCase):
    def setUp(self):
        # Campaign A with two assets
        self.asset_a1 = create_asset()
        self.item_a2 = create_item(
            project=self.asset_a1.item.project, item_id="a2", published=True
        )
        self.asset_a2 = create_asset(item=self.item_a2, slug="asset-a2", published=True)

        # Campaign B with one asset
        self.campaign_b = create_campaign(slug="camp-b")
        self.project_b = create_project(campaign=self.campaign_b, slug="proj-b")
        self.item_b1 = create_item(project=self.project_b, item_id="b1")
        self.asset_b1 = create_asset(item=self.item_b1, slug="asset-b1")

        self.request = HttpRequest()

        class DummyAdmin:
            def __init__(self, model):
                self.model = model
                self.messages = []

            def message_user(self, request, msg, **kwargs):
                self.messages.append((request, msg, kwargs))

        self.DummyAdmin = DummyAdmin

    def test_verify_assets_action_for_campaign(self):
        admin_obj = self.DummyAdmin(model=Campaign)
        queryset = Campaign.objects.filter(
            pk__in=[self.asset_a1.item.project.campaign.pk, self.campaign_b.pk]
        )

        with (
            mock.patch(
                "concordia.admin.actions.uuid.uuid4",
                return_value=uuid.UUID("12345678-1234-1234-1234-1234567890ab"),
            ),
            mock.patch(
                "concordia.admin.actions.create_verify_asset_image_job_batch",
                return_value=(3, "http://example/jobs"),
            ) as mock_batch,
        ):
            verify_assets_action(admin_obj, self.request, queryset)

        # Assert the selected asset IDs were passed through
        passed_ids = list(mock_batch.call_args[0][0])
        self.assertCountEqual(
            passed_ids, [self.asset_a1.pk, self.asset_a2.pk, self.asset_b1.pk]
        )

        # Assert the message content
        self.assertEqual(len(admin_obj.messages), 1)
        _req, msg, _kwargs = admin_obj.messages[0]
        self.assertIn(
            "Created 3 VerifyAssetImageJobs as part of batch "
            "12345678-1234-1234-1234-1234567890ab",
            msg,
        )
        self.assertIn('href="http://example/jobs"', msg)

    def test_verify_assets_action_for_project(self):
        admin_obj = self.DummyAdmin(model=Project)
        queryset = Project.objects.filter(pk__in=[self.asset_a1.item.project.pk])

        with mock.patch(
            "concordia.admin.actions.create_verify_asset_image_job_batch",
            return_value=(2, "http://example/proj"),
        ) as mock_batch:
            verify_assets_action(admin_obj, self.request, queryset)

        passed_ids = list(mock_batch.call_args[0][0])
        self.assertCountEqual(passed_ids, [self.asset_a1.pk, self.asset_a2.pk])

        self.assertEqual(len(admin_obj.messages), 1)
        _req, msg, _kwargs = admin_obj.messages[0]
        self.assertIn("Created 2 VerifyAssetImageJobs", msg)

    def test_verify_assets_action_for_item(self):
        admin_obj = self.DummyAdmin(model=Item)
        queryset = Item.objects.filter(pk__in=[self.asset_a1.item.pk, self.item_b1.pk])

        with mock.patch(
            "concordia.admin.actions.create_verify_asset_image_job_batch",
            return_value=(2, "http://example/item"),
        ) as mock_batch:
            verify_assets_action(admin_obj, self.request, queryset)

        passed_ids = list(mock_batch.call_args[0][0])
        self.assertCountEqual(passed_ids, [self.asset_a1.pk, self.asset_b1.pk])

        self.assertEqual(len(admin_obj.messages), 1)
        _req, msg, _kwargs = admin_obj.messages[0]
        self.assertIn("Created 2 VerifyAssetImageJobs", msg)

    def test_verify_assets_action_for_asset(self):
        admin_obj = self.DummyAdmin(model=Asset)
        queryset = Asset.objects.filter(pk__in=[self.asset_a2.pk, self.asset_b1.pk])

        with mock.patch(
            "concordia.admin.actions.create_verify_asset_image_job_batch",
            return_value=(2, "http://example/asset"),
        ) as mock_batch:
            verify_assets_action(admin_obj, self.request, queryset)

        passed_ids = list(mock_batch.call_args[0][0])
        self.assertCountEqual(passed_ids, [self.asset_a2.pk, self.asset_b1.pk])

        self.assertEqual(len(admin_obj.messages), 1)
        _req, msg, _kwargs = admin_obj.messages[0]
        self.assertIn("Created 2 VerifyAssetImageJobs", msg)

    def test_verify_assets_action_for_unsupported_model(self):
        admin_obj = self.DummyAdmin(model=User)  # unsupported branch
        queryset = User.objects.none()

        with mock.patch(
            "concordia.admin.actions.create_verify_asset_image_job_batch"
        ) as mock_batch:
            verify_assets_action(admin_obj, self.request, queryset)

        # No batch call for unsupported model
        self.assertFalse(mock_batch.called)

        # Error message sent
        self.assertEqual(len(admin_obj.messages), 1)
        _req, msg, kwargs = admin_obj.messages[0]
        self.assertIn("This action is not available for this model.", msg)
        self.assertEqual(kwargs.get("level"), "error")
