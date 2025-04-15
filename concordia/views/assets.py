import logging
import random
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.db.transaction import atomic
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache

from concordia.api_views import APIDetailView
from concordia.forms import TurnstileForm
from concordia.models import (
    Asset,
    AssetTranscriptionReservation,
    Campaign,
    CardFamily,
    Guide,
    Topic,
    TranscriptionStatus,
    TutorialCard,
    UserAssetTagCollection,
)
from concordia.templatetags.concordia_media_tags import asset_media_url
from concordia.utils import (
    get_anonymous_user,
    get_or_create_reservation_token,
)
from concordia.utils.next_asset import (
    find_next_reviewable_campaign_asset,
    find_next_reviewable_topic_asset,
    find_next_transcribable_campaign_asset,
    find_next_transcribable_topic_asset,
    find_reviewable_campaign_asset,
    find_transcribable_campaign_asset,
    remove_next_asset_objects,
)

from .utils import AnonymousUserValidationCheckMixin

logger = logging.getLogger(__name__)


@method_decorator(never_cache, name="dispatch")
class AssetDetailView(AnonymousUserValidationCheckMixin, APIDetailView):
    """
    Class to handle GET ansd POST requests on route /campaigns/<campaign>/asset/<asset>
    """

    template_name = "transcriptions/asset_detail.html"

    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except Http404:
            campaign = get_object_or_404(
                Campaign.objects.published(), slug=self.kwargs["campaign_slug"]
            )
            return redirect(campaign)

    def get_queryset(self):
        asset_qs = Asset.objects.published().filter(
            item__project__campaign__slug=self.kwargs["campaign_slug"],
            item__project__slug=self.kwargs["project_slug"],
            item__item_id=self.kwargs["item_id"],
            slug=self.kwargs["slug"],
        )
        asset_qs = asset_qs.select_related("item__project__campaign")

        return asset_qs

    def get_context_data(self, **kwargs):
        """
        Handle the GET request
        :param kws:
        :return: dictionary of items used in the template
        """

        ctx = super().get_context_data(**kwargs)
        asset = ctx["asset"]
        ctx["item"] = item = asset.item
        ctx["project"] = project = item.project
        ctx["campaign"] = project.campaign

        transcription = asset.transcription_set.order_by("-pk").first()
        ctx["transcription"] = transcription

        ctx["next_open_asset_url"] = "%s?%s" % (
            reverse(
                "transcriptions:redirect-to-next-transcribable-campaign-asset",
                kwargs={"campaign_slug": project.campaign.slug},
            ),
            urlencode(
                {"project": project.slug, "item": item.item_id, "asset": asset.id}
            ),
        )

        ctx["next_review_asset_url"] = "%s?%s" % (
            reverse(
                "transcriptions:redirect-to-next-reviewable-campaign-asset",
                kwargs={"campaign_slug": project.campaign.slug},
            ),
            urlencode(
                {"project": project.slug, "item": item.item_id, "asset": asset.id}
            ),
        )

        # We'll handle the case where an item with no transcriptions should be
        # shown as status=not_started here so the logic doesn't need to be repeated in
        # templates:
        if transcription:
            for choice_key, choice_value in TranscriptionStatus.CHOICE_MAP.items():
                if choice_value == transcription.status:
                    transcription_status = choice_key
        else:
            transcription_status = TranscriptionStatus.NOT_STARTED
        ctx["transcription_status"] = transcription_status

        if (
            transcription_status == TranscriptionStatus.NOT_STARTED
            or transcription_status == TranscriptionStatus.IN_PROGRESS
        ):
            ctx["activity_mode"] = "transcribe"
            ctx["disable_ocr"] = asset.turn_off_ocr()
        else:
            ctx["disable_ocr"] = True
        if transcription_status == TranscriptionStatus.SUBMITTED:
            ctx["activity_mode"] = "review"

        previous_asset = (
            item.asset_set.published()
            .filter(sequence__lt=asset.sequence)
            .order_by("sequence")
            .last()
        )
        next_asset = (
            item.asset_set.published()
            .filter(sequence__gt=asset.sequence)
            .order_by("sequence")
            .first()
        )
        if previous_asset:
            ctx["previous_asset_url"] = previous_asset.get_absolute_url()
        if next_asset:
            ctx["next_asset_url"] = next_asset.get_absolute_url()

        ctx["asset_navigation"] = (
            item.asset_set.published()
            .order_by("sequence")
            .values_list("sequence", "slug")
        )

        image_url = asset_media_url(asset)
        if asset.download_url and "iiif" in asset.download_url:
            thumbnail_url = asset.download_url.replace(
                "http://tile.loc.gov", "https://tile.loc.gov"
            )
            thumbnail_url = thumbnail_url.replace("/pct:100/", "/!512,512/")
        else:
            thumbnail_url = image_url
        ctx["thumbnail_url"] = thumbnail_url

        ctx["current_asset_url"] = self.request.build_absolute_uri()

        tag_groups = UserAssetTagCollection.objects.filter(asset__slug=asset.slug)

        tags = set()

        for tag_group in tag_groups:
            for tag in tag_group.tags.all():
                tags.add(tag.value)

        ctx["tags"] = sorted(tags)

        ctx["registered_contributors"] = asset.get_contributor_count()

        if project.campaign.card_family:
            card_family = project.campaign.card_family
        else:
            card_family = CardFamily.objects.filter(default=True).first()
        if card_family is not None:
            unordered_cards = TutorialCard.objects.filter(tutorial=card_family)
            ordered_cards = unordered_cards.order_by("order")
            ctx["cards"] = [tutorial_card.card for tutorial_card in ordered_cards]

        guides = Guide.objects.order_by("order").values("title", "body")
        if guides.count() > 0:
            ctx["guides"] = guides

        ctx["languages"] = list(settings.LANGUAGE_CODES.items())

        ctx["undo_available"] = asset.can_rollback()[0] if transcription else False
        ctx["redo_available"] = asset.can_rollforward()[0] if transcription else False

        ctx["turnstile_form"] = TurnstileForm(auto_id=False)

        return ctx


def redirect_to_next_asset(asset, mode, request, user):
    """
    Redirects the user to the appropriate asset view or the homepage if no asset is
    available.

    If an asset is found, a reservation is created for it and the asset is removed
    from the relevant caching tables. The user is then redirected to the transcription
    page for that asset.

    If no asset is provided, redirects to the homepage with an informational message.

    Args:
        asset (Asset or None): The asset to redirect to, or None if unavailable.
        mode (str): Either "transcribe" or "review", used for messaging.
        request (HttpRequest): The request initiating the redirect.
        user (User): The user being redirected.

    Returns:
        HttpResponseRedirect: Redirect to the asset or homepage.
    """

    reservation_token = get_or_create_reservation_token(request)
    if asset:
        # We previously created reservations for transcriptions
        # but not reviews. This created a race condition
        # with the next asset caching system because the
        # non-reserved asset could be added into the cache
        # table between when the user was redirected and
        # when they made their own reservation, resulting in
        # that asset being added to the caching system and
        # possibly being sent to another user
        res = AssetTranscriptionReservation(
            asset=asset, reservation_token=reservation_token
        )
        res.full_clean()
        res.save()
        remove_next_asset_objects(asset.id)
        return redirect(
            "transcriptions:asset-detail",
            asset.item.project.campaign.slug,
            asset.item.project.slug,
            asset.item.item_id,
            asset.slug,
        )
    else:
        no_pages_message = f"There are no remaining pages to {mode}."

        messages.info(request, no_pages_message)

        return redirect("homepage")


@never_cache
@atomic
def redirect_to_next_reviewable_asset(request):
    """
    Attempts to redirect the user to a reviewable asset from any active reviewable
    campaign.

    Iterates through campaigns marked as next-reviewable, falling back to others if
    needed. Skips campaigns with no eligible assets. Uses asset caching where possible.

    Returns:
        HttpResponseRedirect: Redirect to the selected asset or homepage.
    """

    if not request.user.is_authenticated:
        user = get_anonymous_user()
    else:
        user = request.user

    campaign_ids = list(
        Campaign.objects.active()
        .listed()
        .published()
        .get_next_review_campaigns()
        .values_list("id", flat=True)
    )

    asset = None
    if campaign_ids:
        random.shuffle(campaign_ids)  # nosec
    else:
        logger.info("No configured reviewable campaigns")

    for campaign_id in campaign_ids:
        try:
            campaign = Campaign.objects.get(id=campaign_id)
        except IndexError:
            logger.error("Next reviewable campaign %s not found", campaign_id)
            continue
        asset = find_reviewable_campaign_asset(campaign, user)
        if asset:
            break
        else:
            logger.info("No reviewable assets found in %s", campaign)

    if not asset:
        for campaign in (
            Campaign.objects.active()
            .listed()
            .published()
            .exclude(id__in=campaign_ids)
            .order_by("launch_date")
        ):
            asset = find_reviewable_campaign_asset(campaign, user)
            if asset:
                break
            else:
                logger.info("No reviewable assets found in %s", campaign)
    return redirect_to_next_asset(asset, "review", request, user)


@never_cache
@atomic
def redirect_to_next_transcribable_asset(request):
    """
    Attempts to redirect the user to a transcribable asset from any active transcription
    campaign.

    Iterates through campaigns marked as next-transcribable, falling back to others if
    needed. Skips campaigns with no eligible assets. Uses asset caching where possible.

    Returns:
        HttpResponseRedirect: Redirect to the selected asset or homepage.
    """

    campaign_ids = list(
        Campaign.objects.active()
        .listed()
        .published()
        .get_next_transcription_campaigns()
        .values_list("id", flat=True)
    )

    asset = None
    if campaign_ids:
        random.shuffle(campaign_ids)  # nosec
    else:
        logger.info("No configured transcribable campaigns")

    for campaign_id in campaign_ids:
        try:
            campaign = Campaign.objects.get(id=campaign_id)
        except IndexError:
            logger.error("Next transcribable campaign %s not found", campaign_id)
            continue
        asset = find_transcribable_campaign_asset(campaign)
        if asset:
            break
        else:
            logger.info("No transcribable assets found in %s", campaign)

    if not asset:
        for campaign in (
            Campaign.objects.active()
            .listed()
            .published()
            .exclude(id__in=campaign_ids)
            .order_by("-launch_date")
        ):
            asset = find_transcribable_campaign_asset(campaign)
            if asset:
                break
            else:
                logger.info("No transcribable assets found in %s", campaign)

    if not asset:
        logger.info("No transcribable assets found in any campaign")

    return redirect_to_next_asset(asset, "transcribe", request, request.user)


@never_cache
@atomic
def redirect_to_next_reviewable_campaign_asset(request, *, campaign_slug):
    """
    Redirects the user to the next reviewable asset within a specified campaign.

    Accepts optional query parameters to influence prioritization:
    - project: Current project slug
    - item: Current item_id (NOT item.id but item.item_id)
    - asset: ID of the most recently reviewed asset

    Args:
        request (HttpRequest): The incoming request.
        campaign_slug (str): Slug for the target campaign.

    Returns:
        HttpResponseRedirect: Redirect to the selected asset or homepage.
    """

    # Campaign is specified: may be listed or unlisted
    campaign = get_object_or_404(Campaign.objects.published(), slug=campaign_slug)
    project_slug = request.GET.get("project", "")
    item_id = request.GET.get("item", "")
    asset_pk = request.GET.get("asset", 0)

    if not request.user.is_authenticated:
        user = get_anonymous_user()
    else:
        user = request.user

    # We pass request.user instead of user here to maintain pre-existing behavior
    # (though it's probably unintended)
    # TODO: Re-evaluate whether we should pass in user instead
    asset = find_next_reviewable_campaign_asset(
        campaign, request.user, project_slug, item_id, asset_pk
    )

    return redirect_to_next_asset(asset, "review", request, user)


@never_cache
@atomic
def redirect_to_next_transcribable_campaign_asset(request, *, campaign_slug):
    """
    Redirects the user to the next transcribable asset within a specified campaign.

    Accepts optional query parameters to influence prioritization:
    - project: Current project slug
    - item: Current item_id (NOT item.id but item.item_id)
    - asset: ID of the most recently transcribed asset

    Args:
        request (HttpRequest): The incoming request.
        campaign_slug (str): Slug for the target campaign.

    Returns:
        HttpResponseRedirect: Redirect to the selected asset or homepage.
    """

    # Campaign is specified: may be listed or unlisted
    campaign = get_object_or_404(Campaign.objects.published(), slug=campaign_slug)
    project_slug = request.GET.get("project", "")
    item_id = request.GET.get("item", "")
    asset_pk = request.GET.get("asset", 0)

    if not request.user.is_authenticated:
        user = get_anonymous_user()
    else:
        user = request.user

    asset = find_next_transcribable_campaign_asset(
        campaign, project_slug, item_id, asset_pk
    )

    return redirect_to_next_asset(asset, "transcribe", request, user)


@never_cache
@atomic
def redirect_to_next_reviewable_topic_asset(request, *, topic_slug):
    """
    Redirects the user to the next reviewable asset within a specified topic.

    Accepts optional query parameters to influence prioritization:
    - project: Current project slug
    - item: Current item_id (NOT item.id but item.item_id)
    - asset: ID of the most recently reviewed asset

    Args:
        request (HttpRequest): The incoming request.
        topic_slug (str): Slug for the target topic.

    Returns:
        HttpResponseRedirect: Redirect to the selected asset or homepage.
    """
    # Topic is specified: may be listed or unlisted
    topic = get_object_or_404(Topic.objects.published(), slug=topic_slug)
    project_slug = request.GET.get("project", "")
    item_id = request.GET.get("item", "")
    asset_pk = request.GET.get("asset", 0)

    if not request.user.is_authenticated:
        user = get_anonymous_user()
    else:
        user = request.user

    # We pass request.user instead of user here to maintain pre-existing behavior
    # (though it's probably unintended)
    # TODO: Re-evaluate whether we should pass in user instead
    asset = find_next_reviewable_topic_asset(
        topic, request.user, project_slug, item_id, asset_pk
    )

    return redirect_to_next_asset(asset, "review", request, user)


@never_cache
@atomic
def redirect_to_next_transcribable_topic_asset(request, *, topic_slug):
    """
    Redirects the user to the next transcribable asset within a specified topic.

    Accepts optional query parameters to influence prioritization:
    - project: Current project slug
    - item: Current item_id (NOT item.id but item.item_id)
    - asset: ID of the most recently transcribed asset

    Args:
        request (HttpRequest): The incoming request.
        topic_slug (str): Slug for the target topic.

    Returns:
        HttpResponseRedirect: Redirect to the selected asset or homepage.
    """

    # Topic is specified: may be listed or unlisted
    topic = get_object_or_404(Topic.objects.published(), slug=topic_slug)
    project_slug = request.GET.get("project", "")
    item_id = request.GET.get("item", "")
    asset_pk = request.GET.get("asset", 0)

    if not request.user.is_authenticated:
        user = get_anonymous_user()
    else:
        user = request.user

    asset = find_next_transcribable_topic_asset(topic, project_slug, item_id, asset_pk)

    return redirect_to_next_asset(asset, "transcribe", request, user)
