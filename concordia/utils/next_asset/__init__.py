from concordia.models import (
    NextReviewableCampaignAsset,
    NextReviewableTopicAsset,
    NextTranscribableCampaignAsset,
    NextTranscribableTopicAsset,
)

from .reviewable import (
    find_and_order_potential_reviewable_campaign_assets,
    find_and_order_potential_reviewable_topic_assets,
    find_new_reviewable_campaign_assets,
    find_new_reviewable_topic_assets,
    find_next_reviewable_campaign_asset,
    find_next_reviewable_campaign_assets,
    find_next_reviewable_topic_asset,
    find_next_reviewable_topic_assets,
    find_reviewable_campaign_asset,
    find_reviewable_topic_asset,
)
from .transcribable import (
    find_and_order_potential_transcribable_campaign_assets,
    find_and_order_potential_transcribable_topic_assets,
    find_new_transcribable_campaign_assets,
    find_new_transcribable_topic_assets,
    find_next_transcribable_campaign_asset,
    find_next_transcribable_campaign_assets,
    find_next_transcribable_topic_asset,
    find_next_transcribable_topic_assets,
    find_transcribable_campaign_asset,
    find_transcribable_topic_asset,
)

__all__ = [
    "find_and_order_potential_transcribable_campaign_assets",
    "find_and_order_potential_transcribable_topic_assets",
    "find_new_transcribable_campaign_assets",
    "find_new_transcribable_topic_assets",
    "find_next_transcribable_campaign_asset",
    "find_next_transcribable_topic_asset",
    "find_next_transcribable_campaign_assets",
    "find_next_transcribable_topic_assets",
    "find_transcribable_campaign_asset",
    "find_transcribable_topic_asset",
    "find_and_order_potential_reviewable_campaign_assets",
    "find_and_order_potential_reviewable_topic_assets",
    "find_new_reviewable_campaign_assets",
    "find_new_reviewable_topic_assets",
    "find_next_reviewable_campaign_assets",
    "find_next_reviewable_topic_assets",
    "find_next_reviewable_campaign_asset",
    "find_next_reviewable_topic_asset",
    "find_reviewable_campaign_asset",
    "find_reviewable_topic_asset",
    "remove_next_asset_objects",
]


def remove_next_asset_objects(asset_id):
    NextTranscribableCampaignAsset.objects.filter(asset_id=asset_id).delete()
    NextTranscribableTopicAsset.objects.filter(asset_id=asset_id).delete()
    NextReviewableCampaignAsset.objects.filter(asset_id=asset_id).delete()
    NextReviewableTopicAsset.objects.filter(asset_id=asset_id).delete()
