from unittest import mock

from django.test import TestCase
from django.utils import timezone

from concordia.models import (
    NextReviewableCampaignAsset,
    NextReviewableTopicAsset,
    NextTranscribableCampaignAsset,
    NextTranscribableTopicAsset,
    TranscriptionStatus,
)
from concordia.tasks.next_asset.renew import renew_next_asset_cache
from concordia.tasks.next_asset.reviewable import (
    clean_next_reviewable_for_campaign,
    clean_next_reviewable_for_topic,
    populate_next_reviewable_for_campaign,
    populate_next_reviewable_for_topic,
)
from concordia.tasks.next_asset.transcribable import (
    clean_next_transcribable_for_campaign,
    clean_next_transcribable_for_topic,
    populate_next_transcribable_for_campaign,
    populate_next_transcribable_for_topic,
)
from concordia.utils import get_anonymous_user

from .utils import (
    CreateTestUsers,
    create_asset,
    create_topic,
    create_transcription,
)


class PopulateNextAssetTasksTests(CreateTestUsers, TestCase):
    def setUp(self):
        self.anon = get_anonymous_user()
        self.user = self.create_test_user()
        self.asset1 = create_asset(slug="test-asset-1", title="Test Asset 1")
        self.asset2 = create_asset(
            item=self.asset1.item, slug="test-asset-2", title="Test Asset 2"
        )
        self.topic = create_topic(project=self.asset1.item.project)
        self.campaign = self.asset1.campaign

    def test_populate_next_transcribable_for_campaign(self):
        populate_next_transcribable_for_campaign(campaign_id=self.campaign.id)
        self.assertEqual(
            NextTranscribableCampaignAsset.objects.filter(
                campaign=self.campaign
            ).count(),
            2,
        )

    def test_populate_next_transcribable_for_topic(self):
        populate_next_transcribable_for_topic(topic_id=self.topic.id)
        self.assertEqual(
            NextTranscribableTopicAsset.objects.filter(topic=self.topic).count(), 2
        )

    def test_populate_next_reviewable_for_campaign(self):
        create_transcription(
            asset=self.asset1, user=self.anon, submitted=timezone.now()
        )
        create_transcription(
            asset=self.asset2, user=self.user, submitted=timezone.now()
        )
        populate_next_reviewable_for_campaign(campaign_id=self.campaign.id)
        self.assertEqual(
            NextReviewableCampaignAsset.objects.filter(campaign=self.campaign).count(),
            2,
        )

    def test_populate_next_reviewable_for_topic(self):
        create_transcription(
            asset=self.asset1, user=self.anon, submitted=timezone.now()
        )
        create_transcription(
            asset=self.asset2, user=self.user, submitted=timezone.now()
        )
        populate_next_reviewable_for_topic(topic_id=self.topic.id)
        self.assertEqual(
            NextReviewableTopicAsset.objects.filter(topic=self.topic).count(), 2
        )

    @mock.patch("concordia.tasks.next_asset.transcribable.logger")
    def test_populate_next_transcribable_for_campaign_missing(self, mock_logger):
        populate_next_transcribable_for_campaign(campaign_id=9999)
        mock_logger.error.assert_called_once()

    @mock.patch("concordia.tasks.next_asset.transcribable.logger")
    def test_populate_next_transcribable_for_topic_missing(self, mock_logger):
        populate_next_transcribable_for_topic(topic_id=9999)
        mock_logger.error.assert_called_once()

    @mock.patch("concordia.tasks.next_asset.reviewable.logger")
    def test_populate_next_reviewable_for_campaign_missing(self, mock_logger):
        populate_next_reviewable_for_campaign(campaign_id=9999)
        mock_logger.error.assert_called_once()

    @mock.patch("concordia.tasks.next_asset.reviewable.logger")
    def test_populate_next_reviewable_for_topic_missing(self, mock_logger):
        populate_next_reviewable_for_topic(topic_id=9999)
        mock_logger.error.assert_called_once()

    @mock.patch("concordia.tasks.next_asset.transcribable.logger")
    def test_populate_next_transcribable_for_campaign_none_needed(self, mock_logger):
        for i in range(3, 103):
            asset = create_asset(item=self.asset1.item, slug=f"dummy-{i}")
            NextTranscribableCampaignAsset.objects.create(
                asset=asset,
                item=asset.item,
                item_item_id=asset.item.item_id,
                project=asset.item.project,
                project_slug=asset.item.project.slug,
                campaign=self.campaign,
                sequence=asset.sequence,
                transcription_status=asset.transcription_status,
            )
        populate_next_transcribable_for_campaign(campaign_id=self.campaign.id)
        mock_logger.info.assert_any_call(
            "Campaign %s already has %s next transcribable assets", self.campaign, 100
        )

    @mock.patch("concordia.tasks.next_asset.transcribable.logger")
    def test_populate_next_transcribable_for_topic_none_needed(self, mock_logger):
        for i in range(3, 103):
            asset = create_asset(item=self.asset1.item, slug=f"dummy-{i}")
            NextTranscribableTopicAsset.objects.create(
                asset=asset,
                item=asset.item,
                item_item_id=asset.item.item_id,
                project=asset.item.project,
                project_slug=asset.item.project.slug,
                topic=self.topic,
                sequence=asset.sequence,
                transcription_status=asset.transcription_status,
            )
        populate_next_transcribable_for_topic(topic_id=self.topic.id)
        mock_logger.info.assert_any_call(
            "Topic %s already has %s next transcribable assets", self.topic, 100
        )

    @mock.patch("concordia.tasks.next_asset.reviewable.logger")
    def test_populate_next_reviewable_for_campaign_none_needed(self, mock_logger):
        create_transcription(
            asset=self.asset1, user=self.user, submitted=timezone.now()
        )
        for i in range(3, 103):
            asset = create_asset(item=self.asset1.item, slug=f"r-{i}")
            create_transcription(asset=asset, user=self.user, submitted=timezone.now())
            NextReviewableCampaignAsset.objects.create(
                asset=asset,
                item=asset.item,
                item_item_id=asset.item.item_id,
                project=asset.item.project,
                project_slug=asset.item.project.slug,
                campaign=self.campaign,
                sequence=asset.sequence,
                transcriber_ids=[self.user.id],
            )

        populate_next_reviewable_for_campaign(campaign_id=self.campaign.id)
        mock_logger.info.assert_any_call(
            "Campaign %s already has %s next reviewable assets", self.campaign, 100
        )

    @mock.patch("concordia.tasks.next_asset.reviewable.logger")
    def test_populate_next_reviewable_for_topic_none_needed(self, mock_logger):
        create_transcription(
            asset=self.asset1, user=self.user, submitted=timezone.now()
        )
        for i in range(3, 103):
            asset = create_asset(item=self.asset1.item, slug=f"t-{i}")
            create_transcription(asset=asset, user=self.user, submitted=timezone.now())
            NextReviewableTopicAsset.objects.create(
                asset=asset,
                item=asset.item,
                item_item_id=asset.item.item_id,
                project=asset.item.project,
                project_slug=asset.item.project.slug,
                topic=self.topic,
                sequence=asset.sequence,
                transcriber_ids=[self.user.id],
            )

        populate_next_reviewable_for_topic(topic_id=self.topic.id)
        mock_logger.info.assert_any_call(
            "Topic %s already has %s next reviewable assets", self.topic, 100
        )

    @mock.patch("concordia.tasks.next_asset.reviewable.logger")
    def test_populate_next_reviewable_for_campaign_none_found(self, mock_logger):
        create_transcription(
            asset=self.asset1, user=self.user, submitted=timezone.now()
        )

        NextReviewableCampaignAsset.objects.create(
            asset=self.asset1,
            item=self.asset1.item,
            item_item_id=self.asset1.item.item_id,
            project=self.asset1.item.project,
            project_slug=self.asset1.item.project.slug,
            campaign=self.campaign,
            sequence=self.asset1.sequence,
            transcriber_ids=[self.user.id],
        )

        populate_next_reviewable_for_campaign(campaign_id=self.campaign.id)
        mock_logger.info.assert_any_call(
            "No reviewable assets found in campaign %s", self.campaign
        )

    @mock.patch("concordia.tasks.next_asset.reviewable.logger")
    def test_populate_next_reviewable_for_topic_none_found(self, mock_logger):
        create_transcription(
            asset=self.asset1, user=self.user, submitted=timezone.now()
        )

        NextReviewableTopicAsset.objects.create(
            asset=self.asset1,
            item=self.asset1.item,
            item_item_id=self.asset1.item.item_id,
            project=self.asset1.item.project,
            project_slug=self.asset1.item.project.slug,
            topic=self.topic,
            sequence=self.asset1.sequence,
            transcriber_ids=[self.user.id],
        )

        populate_next_reviewable_for_topic(topic_id=self.topic.id)
        mock_logger.info.assert_any_call(
            "No reviewable assets found in topic %s", self.topic
        )

    @mock.patch("concordia.tasks.next_asset.transcribable.logger")
    def test_populate_next_transcribable_for_campaign_none_found(self, mock_logger):
        for asset in (self.asset1, self.asset2):
            NextTranscribableCampaignAsset.objects.create(
                asset=asset,
                item=asset.item,
                item_item_id=asset.item.item_id,
                project=asset.item.project,
                project_slug=asset.item.project.slug,
                campaign=self.campaign,
                sequence=asset.sequence,
                transcription_status=asset.transcription_status,
            )

        populate_next_transcribable_for_campaign(campaign_id=self.campaign.id)
        mock_logger.info.assert_any_call(
            "No transcribable assets found in campaign %s", self.campaign
        )

    @mock.patch("concordia.tasks.next_asset.transcribable.logger")
    def test_populate_next_transcribable_for_topic_none_found(self, mock_logger):
        for asset in (self.asset1, self.asset2):
            NextTranscribableTopicAsset.objects.create(
                asset=asset,
                item=asset.item,
                item_item_id=asset.item.item_id,
                project=asset.item.project,
                project_slug=asset.item.project.slug,
                topic=self.topic,
                sequence=asset.sequence,
                transcription_status=asset.transcription_status,
            )

        populate_next_transcribable_for_topic(topic_id=self.topic.id)
        mock_logger.info.assert_any_call(
            "No transcribable assets found in topic %s", self.topic
        )


class CleanNextAssetTasksTests(TestCase):
    def setUp(self):
        self.asset = create_asset()
        self.campaign = self.asset.campaign
        self.topic = create_topic(project=self.asset.item.project)
        self.campaign_transcribable = NextTranscribableCampaignAsset.objects.create(
            asset=self.asset,
            item=self.asset.item,
            item_item_id=self.asset.item.item_id,
            project=self.asset.item.project,
            project_slug=self.asset.item.project.slug,
            campaign=self.campaign,
            sequence=self.asset.sequence,
            transcription_status=TranscriptionStatus.NOT_STARTED,
        )
        self.topic_transcribable = NextTranscribableTopicAsset.objects.create(
            asset=self.asset,
            item=self.asset.item,
            item_item_id=self.asset.item.item_id,
            project=self.asset.item.project,
            project_slug=self.asset.item.project.slug,
            topic=self.topic,
            sequence=self.asset.sequence,
            transcription_status=TranscriptionStatus.IN_PROGRESS,
        )
        self.campaign_reviewable = NextReviewableCampaignAsset.objects.create(
            asset=self.asset,
            item=self.asset.item,
            item_item_id=self.asset.item.item_id,
            project=self.asset.item.project,
            project_slug=self.asset.item.project.slug,
            campaign=self.campaign,
            sequence=self.asset.sequence,
        )
        self.topic_reviewable = NextReviewableTopicAsset.objects.create(
            asset=self.asset,
            item=self.asset.item,
            item_item_id=self.asset.item.item_id,
            project=self.asset.item.project,
            project_slug=self.asset.item.project.slug,
            topic=self.topic,
            sequence=self.asset.sequence,
        )

    @mock.patch(
        "concordia.tasks.next_asset.transcribable.populate_next_transcribable_for_campaign.delay"
    )
    def test_clean_next_transcribable_for_campaign(self, mock_delay):
        self.asset.transcription_status = TranscriptionStatus.COMPLETED
        self.asset.save()
        clean_next_transcribable_for_campaign(self.campaign.id)
        self.assertFalse(
            NextTranscribableCampaignAsset.objects.filter(
                campaign=self.campaign
            ).exists()
        )
        mock_delay.assert_called_once_with(self.campaign.id)

    @mock.patch(
        "concordia.tasks.next_asset.transcribable.populate_next_transcribable_for_topic.delay"
    )
    def test_clean_next_transcribable_for_topic(self, mock_delay):
        self.asset.transcription_status = TranscriptionStatus.COMPLETED
        self.asset.save()
        clean_next_transcribable_for_topic(self.topic.id)
        self.assertFalse(
            NextTranscribableTopicAsset.objects.filter(topic=self.topic).exists()
        )
        mock_delay.assert_called_once_with(self.topic.id)

    @mock.patch(
        "concordia.tasks.next_asset.reviewable.populate_next_reviewable_for_campaign.delay"
    )
    def test_clean_next_reviewable_for_campaign(self, mock_delay):
        self.asset.transcription_status = TranscriptionStatus.IN_PROGRESS
        self.asset.save()
        clean_next_reviewable_for_campaign(self.campaign.id)
        self.assertFalse(
            NextReviewableCampaignAsset.objects.filter(campaign=self.campaign).exists()
        )
        mock_delay.assert_called_once_with(self.campaign.id)

    @mock.patch(
        "concordia.tasks.next_asset.reviewable.populate_next_reviewable_for_topic.delay"
    )
    def test_clean_next_reviewable_for_topic(self, mock_delay):
        self.asset.transcription_status = TranscriptionStatus.NOT_STARTED
        self.asset.save()
        clean_next_reviewable_for_topic(self.topic.id)
        self.assertFalse(
            NextReviewableTopicAsset.objects.filter(topic=self.topic).exists()
        )
        mock_delay.assert_called_once_with(self.topic.id)

    @mock.patch(
        "concordia.tasks.next_asset.reviewable.clean_next_reviewable_for_campaign.delay"
    )
    @mock.patch(
        "concordia.tasks.next_asset.transcribable.clean_next_transcribable_for_campaign.delay"
    )
    @mock.patch(
        "concordia.tasks.next_asset.reviewable.clean_next_reviewable_for_topic.delay"
    )
    @mock.patch(
        "concordia.tasks.next_asset.transcribable.clean_next_transcribable_for_topic.delay"
    )
    def test_renew_next_asset_cache(
        self,
        mock_clean_trans_topic,
        mock_clean_rev_topic,
        mock_clean_trans_campaign,
        mock_clean_rev_campaign,
    ):
        renew_next_asset_cache()
        mock_clean_trans_campaign.assert_called_once_with(campaign_id=self.campaign.id)
        mock_clean_rev_campaign.assert_called_once_with(campaign_id=self.campaign.id)
        mock_clean_trans_topic.assert_called_once_with(topic_id=self.topic.id)
        mock_clean_rev_topic.assert_called_once_with(topic_id=self.topic.id)

    @mock.patch("concordia.tasks.next_asset.transcribable.logger")
    def test_clean_next_transcribable_for_campaign_exception(self, mock_logger):
        with mock.patch.object(
            self.campaign_transcribable, "delete", side_effect=Exception("fail")
        ):
            with mock.patch(
                "concordia.tasks.next_asset.transcribable.find_invalid_next_transcribable_campaign_assets",
                return_value=[self.campaign_transcribable],
            ):
                clean_next_transcribable_for_campaign(self.campaign.id)
        mock_logger.exception.assert_called_once()

    @mock.patch("concordia.tasks.next_asset.transcribable.logger")
    def test_clean_next_transcribable_for_topic_exception(self, mock_logger):
        with mock.patch.object(
            self.topic_transcribable, "delete", side_effect=Exception("fail")
        ):
            with mock.patch(
                "concordia.tasks.next_asset.transcribable.find_invalid_next_transcribable_topic_assets",
                return_value=[self.topic_transcribable],
            ):
                clean_next_transcribable_for_topic(self.topic.id)
        mock_logger.exception.assert_called_once()

    @mock.patch("concordia.tasks.next_asset.reviewable.logger")
    def test_clean_next_reviewable_for_campaign_exception(self, mock_logger):
        with mock.patch.object(
            self.campaign_reviewable, "delete", side_effect=Exception("fail")
        ):
            with mock.patch(
                "concordia.tasks.next_asset.reviewable.find_invalid_next_reviewable_campaign_assets",
                return_value=[self.campaign_reviewable],
            ):
                clean_next_reviewable_for_campaign(self.campaign.id)
        mock_logger.exception.assert_called_once()

    @mock.patch("concordia.tasks.next_asset.reviewable.logger")
    def test_clean_next_reviewable_for_topic_exception(self, mock_logger):
        with mock.patch.object(
            self.topic_reviewable, "delete", side_effect=Exception("fail")
        ):
            with mock.patch(
                "concordia.tasks.next_asset.reviewable.find_invalid_next_reviewable_topic_assets",
                return_value=[self.topic_reviewable],
            ):
                clean_next_reviewable_for_topic(self.topic.id)
        mock_logger.exception.assert_called_once()
