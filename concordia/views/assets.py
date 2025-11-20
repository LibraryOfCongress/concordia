import logging
import random
from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import QuerySet
from django.db.transaction import atomic
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django_ratelimit.decorators import ratelimit

from concordia.api_views import APIDetailView
from concordia.forms import TurnstileForm
from concordia.logging import ConcordiaLogger
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

from .decorators import next_asset_rate
from .utils import AnonymousUserValidationCheckMixin

logger = logging.getLogger(__name__)
structured_logger = ConcordiaLogger.get_logger(__name__)


@method_decorator(never_cache, name="dispatch")
class AssetDetailView(AnonymousUserValidationCheckMixin, APIDetailView):
    """
    Display details for a single asset and handle missing assets.

    This view handles `GET` and `POST` requests by retrieving the published
    `Asset` that matches the campaign, project and item.

    It uses `AnonymousUserValidationCheckMixin` for anonymous-user validation
    and `APIDetailView` for API-driven detail behavior. It overrides
    `dispatch` to log and redirect to the parent campaign page if the asset
    is not found.

    Attributes:
        template_name (str): Template used to render the asset detail page.
    """

    template_name = "transcriptions/asset_detail.html"

    def dispatch(
        self,
        request: HttpRequest,
        *args: Any,
        **kwargs: Any,
    ) -> HttpResponse:
        try:
            return super().dispatch(request, *args, **kwargs)
        except Http404:
            structured_logger.info(
                "AssetDetailView: asset not found, redirecting to campaign " "page.",
                event_code="asset_detail_not_found_redirect",
                user=request.user,
                campaign_slug=self.kwargs.get("campaign_slug"),
                project_slug=self.kwargs.get("project_slug"),
                item_id=self.kwargs.get("item_id"),
                asset_slug=self.kwargs.get("slug"),
            )
            campaign = get_object_or_404(
                Campaign.objects.published(), slug=self.kwargs["campaign_slug"]
            )
            return redirect(campaign)

    def get_queryset(self) -> QuerySet[Asset]:
        asset_qs = Asset.objects.published().filter(
            item__project__campaign__slug=self.kwargs["campaign_slug"],
            item__project__slug=self.kwargs["project_slug"],
            item__item_id=self.kwargs["item_id"],
            slug=self.kwargs["slug"],
        )
        asset_qs = asset_qs.select_related("item__project__campaign")

        return asset_qs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """
        Build the context for the asset detail template.

        Constructs a dictionary with the entries described in the context
        format.

        Context Format:
            - `asset` (Asset): Asset instance being viewed.
            - `item` (Item): Parent item of the asset.
            - `project` (Project): Parent project of the item.
            - `campaign` (Campaign): Campaign that contains the project.
            - `transcription` (Transcription | None): Latest transcription or
              `None`.
            - `next_open_asset_url` (str): URL to the next transcribable
              asset.
            - `next_review_asset_url` (str): URL to the next reviewable
              asset.
            - `transcription_status` (str): One of the keys from
              `TranscriptionStatus`.
            - `activity_mode` (str): `"transcribe"` or `"review"`, based on
              the transcription status.
            - `disable_ocr` (bool): Whether OCR should be disabled for this
              asset.
            - `previous_asset_url` (str | None): URL to the previous asset, if
              any.
            - `next_asset_url` (str | None): URL to the next asset, if any.
            - `asset_navigation` (list[tuple[int, str]]): Sequence and slug
              pairs for navigation.
            - `thumbnail_url` (str): URL of the asset thumbnail image.
            - `current_asset_url` (str): Absolute URL of this asset detail
              view.
            - `tags` (list[str]): Sorted tag values applied to the asset.
            - `registered_contributors` (int): Number of users who have
              contributed to the asset.
            - `cards` (list[Card]): Tutorial cards for the campaign or the
              default card set.
            - `guides` (QuerySet[dict[str, Any]] | None): Tutorial guide
              entries.
            - `languages` (list[tuple[str, str]]): Supported language
              code and name pairs.
            - `undo_available` (bool): Whether a rollback is possible.
            - `redo_available` (bool): Whether a rollforward is possible.
            - `turnstile_form` (TurnstileForm): Form for the Turnstile
              widget.

        Args:
            **kwargs (Any): Additional keyword arguments passed to the
                superclass implementation.

        Returns:
            dict[str, Any]: Context data for rendering the asset detail page.
        """

        ctx = super().get_context_data(**kwargs)
        asset = ctx["asset"]
        # Bind a new logger so asset and user are always included
        context_logger = structured_logger.bind(user=self.request.user, asset=asset)
        context_logger.info(
            "AssetDetailView: building context.",
            event_code="asset_detail_context_start",
        )
        ctx["item"] = item = asset.item
        ctx["project"] = project = item.project
        ctx["campaign"] = project.campaign

        transcription = asset.transcription_set.order_by("-pk").first()
        context_logger.debug(
            "AssetDetailView: latest transcription selected.",
            event_code="asset_detail_latest_transcription",
            transcription=transcription,
        )
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

        # We handle the case where an item with no transcriptions should be
        # shown as status=not_started here so the logic does not need to be
        # repeated in templates.
        if transcription:
            for choice_key, choice_value in TranscriptionStatus.CHOICE_MAP.items():
                if choice_value == transcription.status:
                    transcription_status = choice_key
        else:
            transcription_status = TranscriptionStatus.NOT_STARTED
        ctx["transcription_status"] = transcription_status

        context_logger.debug(
            "AssetDetailView: computed transcription status.",
            event_code="asset_detail_transcription_status",
            computed_status=transcription_status,
            asset_status=asset.transcription_status,
        )

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
        context_logger.debug(
            "AssetDetailView: asset navigation resolved.",
            event_code="asset_detail_navigation",
            previous_asset_id=getattr(previous_asset, "pk", None),
            next_asset_id=getattr(next_asset, "pk", None),
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
        context_logger.debug(
            "AssetDetailView: thumbnail URL determined.",
            event_code="asset_detail_thumbnail",
            thumbnail_url=thumbnail_url,
        )
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

        context_logger.info(
            "AssetDetailView: context ready.",
            event_code="asset_detail_context_ready",
            transcription=transcription,
            transcription_status=transcription_status,
        )
        return ctx


def redirect_to_next_asset(
    asset: Asset | None,
    mode: str,
    request: HttpRequest,
    user: User,
) -> HttpResponseRedirect:
    """
    Redirect the user to the appropriate asset view or the homepage.

    If an asset is found, this helper creates a reservation for it and
    removes the asset from the relevant caching tables. The user is then
    redirected to the transcription page for that asset.

    If no asset is provided, it redirects to the homepage and adds an
    informational message.

    Args:
        asset (Asset | None): Asset to redirect to, or `None` if no asset is
            available.
        mode (str): Either `"transcribe"` or `"review"`, used for messaging.
        request (HttpRequest): Request that initiated the redirect.
        user (User): User being redirected.

    Returns:
        HttpResponseRedirect: Redirect to the asset detail page or the
        homepage.
    """
    structured_logger.info(
        "Starting redirect to next asset.",
        event_code="redirect_next_asset_start",
        user=user,
        mode=mode,
        asset=asset,
    )
    reservation_token = get_or_create_reservation_token(request)
    if asset:
        # We previously created reservations for transcriptions but not
        # reviews. This created a race condition with the next asset caching
        # system because the non-reserved asset could be added into the cache
        # table between when the user was redirected and when they made their
        # own reservation. That could result in the asset being added to the
        # caching system and sent to another user.
        res = AssetTranscriptionReservation(
            asset=asset, reservation_token=reservation_token
        )
        res.full_clean()
        res.save()
        structured_logger.info(
            "Asset reserved and redirecting to asset detail view.",
            event_code="redirect_next_asset_success",
            asset=asset,
            user=user,
        )
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
        structured_logger.warning(
            "No available asset to redirect to.",
            event_code="redirect_next_asset_empty",
            reason=("There were no eligible assets found to assign to the user."),
            reason_code="no_asset_available",
            asset=asset,
            user=user,
            mode=mode,
        )
        messages.info(request, no_pages_message)

        return redirect("homepage")


@ratelimit(
    key="header:cf-connecting-ip",
    rate=next_asset_rate,
    group="next_asset",
    block=True,
)
@never_cache
@atomic
def redirect_to_next_reviewable_asset(
    request: HttpRequest,
) -> HttpResponseRedirect:
    """
    Redirect the user to a reviewable asset from any active reviewable
    campaign.

    This view iterates through campaigns marked as next-reviewable, then
    falls back to other active campaigns if needed. It skips campaigns with
    no eligible assets and uses asset caching when possible.

    Args:
        request (HttpRequest): Incoming HTTP request.

    Returns:
        HttpResponseRedirect: Redirect to the selected asset or the
        homepage.
    """
    structured_logger.info(
        "Entered redirect_to_next_reviewable_asset view.",
        event_code="redirect_reviewable_entry",
        user=request.user,
    )
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
    structured_logger.debug(
        "Fetched candidate campaign IDs for reviewable assets.",
        event_code="redirect_reviewable_campaign_ids",
        user=user,
        campaign_ids=campaign_ids,
    )
    asset = None
    if campaign_ids:
        random.shuffle(campaign_ids)  # nosec
    else:
        logger.info("No configured reviewable campaigns")
        structured_logger.info(
            "No configured reviewable campaigns.",
            event_code="redirect_reviewable_no_campaigns",
            user=user,
        )

    for campaign_id in campaign_ids:
        try:
            campaign = Campaign.objects.get(id=campaign_id)
        except IndexError:
            logger.error("Next reviewable campaign %s not found", campaign_id)
            structured_logger.error(
                "Failed to retrieve next reviewable campaign by ID.",
                event_code="redirect_reviewable_campaign_missing",
                reason=("Reviewable campaign with specified ID was not found."),
                reason_code="reviewable_campaign_not_found",
                user=user,
                campaign_id=campaign_id,
            )
            continue
        asset = find_reviewable_campaign_asset(campaign, user)
        if asset:
            break
        else:
            logger.info("No reviewable assets found in %s", campaign)
            structured_logger.info(
                "No reviewable assets found in campaign.",
                event_code="redirect_reviewable_campaign_empty_primary",
                user=user,
                campaign=campaign,
            )

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
                structured_logger.info(
                    "No reviewable assets found in campaign.",
                    event_code="redirect_reviewable_campaign_empty_fallback",
                    user=user,
                    campaign=campaign,
                )
    structured_logger.info(
        "Redirecting to next reviewable asset.",
        event_code="redirect_reviewable_success",
        user=user,
        asset=asset,
    )
    return redirect_to_next_asset(asset, "review", request, user)


@ratelimit(
    key="header:cf-connecting-ip",
    rate=next_asset_rate,
    group="next_asset",
    block=True,
)
@never_cache
@atomic
def redirect_to_next_transcribable_asset(
    request: HttpRequest,
) -> HttpResponseRedirect:
    """
    Redirect the user to a transcribable asset from any active transcription
    campaign.

    This view iterates through campaigns marked as next-transcribable, then
    falls back to other active campaigns if needed. It skips campaigns with
    no eligible assets and uses asset caching when possible.

    Args:
        request (HttpRequest): Incoming HTTP request.

    Returns:
        HttpResponseRedirect: Redirect to the selected asset or the
        homepage.
    """
    structured_logger.info(
        "Entered redirect_to_next_transcribable_asset view.",
        event_code="redirect_transcribable_entry",
        user=request.user,
    )
    campaign_ids = list(
        Campaign.objects.active()
        .listed()
        .published()
        .get_next_transcription_campaigns()
        .values_list("id", flat=True)
    )
    structured_logger.debug(
        "Fetched candidate campaign IDs for transcribable assets.",
        event_code="redirect_transcribable_campaign_ids",
        user=request.user,
        campaign_ids=campaign_ids,
    )
    asset = None
    if campaign_ids:
        random.shuffle(campaign_ids)  # nosec
    else:
        logger.info("No configured transcribable campaigns")
        structured_logger.info(
            "No configured transcribable campaigns.",
            event_code="redirect_transcribable_no_campaigns",
            user=request.user,
        )

    for campaign_id in campaign_ids:
        try:
            campaign = Campaign.objects.get(id=campaign_id)
        except IndexError:
            logger.error("Next transcribable campaign %s not found", campaign_id)
            structured_logger.error(
                "Next transcribable campaign ID not found.",
                event_code="redirect_transcribable_campaign_missing",
                reason=("Transcribable campaign with specified ID was not found."),
                reason_code="transcribable_campaign_not_found",
                user=request.user,
                campaign_id=campaign_id,
            )
            continue
        asset = find_transcribable_campaign_asset(campaign)
        if asset:
            break
        else:
            logger.info("No transcribable assets found in %s", campaign)
            structured_logger.info(
                "No transcribable assets found in campaign.",
                event_code="redirect_transcribable_campaign_empty_primary",
                user=request.user,
                campaign=campaign,
            )

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
                structured_logger.info(
                    "No transcribable assets found in campaign (fallback " "loop).",
                    event_code="redirect_transcribable_campaign_empty_fallback",
                    user=request.user,
                    campaign=campaign,
                )

    if not asset:
        logger.info("No transcribable assets found in any campaign")
        structured_logger.info(
            "No transcribable assets found in any campaign.",
            event_code="redirect_transcribable_no_assets_anywhere",
            user=request.user,
        )

    structured_logger.info(
        "Redirecting to next transcribable asset.",
        event_code="redirect_transcribable_success",
        user=request.user,
        asset=asset,
    )
    return redirect_to_next_asset(asset, "transcribe", request, request.user)


@ratelimit(
    key="header:cf-connecting-ip",
    rate=next_asset_rate,
    group="next_asset",
    block=True,
)
@never_cache
@atomic
def redirect_to_next_reviewable_campaign_asset(
    request: HttpRequest,
    *,
    campaign_slug: str,
) -> HttpResponseRedirect:
    """
    Redirect the user to the next reviewable asset within a campaign.

    This view redirects within a specific campaign, which may be listed or
    unlisted. It can use optional query parameters to influence which asset
    is prioritized.

    Request Parameters:
        project (str): Current project slug.
        item (str): Current item identifier. This is `item_id`, not the item
            primary key.
        asset (int): ID of the most recently reviewed asset.

    Args:
        request (HttpRequest): Incoming HTTP request.
        campaign_slug (str): Slug for the target campaign.

    Returns:
        HttpResponseRedirect: Redirect to the selected asset or the
        homepage.
    """
    structured_logger.info(
        "Entered redirect_to_next_reviewable_campaign_asset view.",
        event_code="redirect_reviewable_campaign_entry",
        user=request.user,
        campaign_slug=campaign_slug,
    )
    # Campaign is specified: may be listed or unlisted
    campaign = get_object_or_404(Campaign.objects.published(), slug=campaign_slug)
    project_slug = request.GET.get("project", "")
    item_id = request.GET.get("item", "")
    asset_pk = request.GET.get("asset", 0)
    structured_logger.debug(
        "Parsed query parameters for reviewable asset redirection.",
        event_code="redirect_reviewable_campaign_query_params",
        user=request.user,
        campaign=campaign,
        project_slug=project_slug,
        item_id=item_id,
        asset_pk=asset_pk,
    )

    if not request.user.is_authenticated:
        user = get_anonymous_user()
    else:
        user = request.user

    # We pass request.user instead of user here to maintain pre-existing
    # behavior (though it is probably unintended).
    # TODO: Re-evaluate whether we should pass in user instead.
    asset = find_next_reviewable_campaign_asset(
        campaign, request.user, project_slug, item_id, asset_pk
    )
    structured_logger.info(
        "Redirecting to next reviewable asset in campaign.",
        event_code="redirect_reviewable_campaign_success",
        user=user,
        request_user=request.user,
        asset=asset,
        campaign=campaign,  # We log campaign because asset might be None.
    )
    return redirect_to_next_asset(asset, "review", request, user)


@ratelimit(
    key="header:cf-connecting-ip",
    rate=next_asset_rate,
    group="next_asset",
    block=True,
)
@never_cache
@atomic
def redirect_to_next_transcribable_campaign_asset(
    request: HttpRequest,
    *,
    campaign_slug: str,
) -> HttpResponseRedirect:
    """
    Redirect the user to the next transcribable asset within a campaign.

    This view redirects within a specific campaign, which may be listed or
    unlisted. It can use optional query parameters to influence which asset
    is prioritized.

    Request Parameters:
        project (str): Current project slug.
        item (str): Current item identifier. This is `item_id`, not the item
            primary key.
        asset (int): ID of the most recently transcribed asset.

    Args:
        request (HttpRequest): Incoming HTTP request.
        campaign_slug (str): Slug for the target campaign.

    Returns:
        HttpResponseRedirect: Redirect to the selected asset or the
        homepage.
    """
    structured_logger.info(
        "Entered redirect_to_next_transcribable_campaign_asset view.",
        event_code="redirect_transcribable_campaign_entry",
        user=request.user,
        campaign_slug=campaign_slug,
    )
    # Campaign is specified: may be listed or unlisted
    campaign = get_object_or_404(Campaign.objects.published(), slug=campaign_slug)
    project_slug = request.GET.get("project", "")
    item_id = request.GET.get("item", "")
    asset_pk = request.GET.get("asset", 0)
    structured_logger.debug(
        "Parsed query parameters for transcribable asset redirection.",
        event_code="redirect_transcribable_campaign_query_params",
        user=request.user,
        campaign=campaign,
        project_slug=project_slug,
        item_id=item_id,
        asset_pk=asset_pk,
    )

    if not request.user.is_authenticated:
        user = get_anonymous_user()
    else:
        user = request.user

    asset = find_next_transcribable_campaign_asset(
        campaign, project_slug, item_id, asset_pk
    )
    structured_logger.info(
        "Redirecting to next transcribable asset in campaign.",
        event_code="redirect_transcribable_campaign_success",
        user=user,
        asset=asset,
        campaign=campaign,  # We log campaign because asset may be None.
    )
    return redirect_to_next_asset(asset, "transcribe", request, user)


@ratelimit(
    key="header:cf-connecting-ip",
    rate=next_asset_rate,
    group="next_asset",
    block=True,
)
@never_cache
@atomic
def redirect_to_next_reviewable_topic_asset(
    request: HttpRequest,
    *,
    topic_slug: str,
) -> HttpResponseRedirect:
    """
    Redirect the user to the next reviewable asset within a topic.

    This view redirects within a specific topic, which may be listed or
    unlisted. It can use optional query parameters to influence which asset
    is prioritized.

    Request Parameters:
        project (str): Current project slug.
        item (str): Current item identifier. This is `item_id`, not the item
            primary key.
        asset (int): ID of the most recently reviewed asset.

    Args:
        request (HttpRequest): Incoming HTTP request.
        topic_slug (str): Slug for the target topic.

    Returns:
        HttpResponseRedirect: Redirect to the selected asset or the
        homepage.
    """
    structured_logger.info(
        "Entered redirect_to_next_reviewable_topic_asset view.",
        event_code="redirect_reviewable_topic_entry",
        user=request.user,
        topic_slug=topic_slug,
    )
    # Topic is specified: may be listed or unlisted
    topic = get_object_or_404(Topic.objects.published(), slug=topic_slug)
    project_slug = request.GET.get("project", "")
    item_id = request.GET.get("item", "")
    asset_pk = request.GET.get("asset", 0)
    structured_logger.debug(
        "Parsed query parameters for reviewable topic redirection.",
        event_code="redirect_reviewable_topic_query_params",
        user=request.user,
        topic=topic,
        project_slug=project_slug,
        item_id=item_id,
        asset_pk=asset_pk,
    )

    if not request.user.is_authenticated:
        user = get_anonymous_user()
    else:
        user = request.user

    # We pass request.user instead of user here to maintain pre-existing
    # behavior (though it is probably unintended).
    # TODO: Re-evaluate whether we should pass in user instead.
    asset = find_next_reviewable_topic_asset(
        topic, request.user, project_slug, item_id, asset_pk
    )
    structured_logger.info(
        "Redirecting to next reviewable asset in topic.",
        event_code="redirect_reviewable_topic_success",
        user=user,
        request_user=request.user,
        asset=asset,
        topic=topic,
    )

    return redirect_to_next_asset(asset, "review", request, user)


@ratelimit(
    key="header:cf-connecting-ip",
    rate=next_asset_rate,
    group="next_asset",
    block=True,
)
@never_cache
@atomic
def redirect_to_next_transcribable_topic_asset(
    request: HttpRequest,
    *,
    topic_slug: str,
) -> HttpResponseRedirect:
    """
    Redirect the user to the next transcribable asset within a topic.

    This view redirects within a specific topic, which may be listed or
    unlisted. It can use optional query parameters to influence which asset
    is prioritized.

    Request Parameters:
        project (str): Current project slug.
        item (str): Current item identifier. This is `item_id`, not the item
            primary key.
        asset (int): ID of the most recently transcribed asset.

    Args:
        request (HttpRequest): Incoming HTTP request.
        topic_slug (str): Slug for the target topic.

    Returns:
        HttpResponseRedirect: Redirect to the selected asset or the
        homepage.
    """
    structured_logger.info(
        "Entered redirect_to_next_transcribable_topic_asset view.",
        event_code="redirect_transcribable_topic_entry",
        user=request.user,
        topic_slug=topic_slug,
    )
    # Topic is specified: may be listed or unlisted
    topic = get_object_or_404(Topic.objects.published(), slug=topic_slug)
    project_slug = request.GET.get("project", "")
    item_id = request.GET.get("item", "")
    asset_pk = request.GET.get("asset", 0)
    structured_logger.debug(
        "Parsed query parameters for transcribable topic redirection.",
        event_code="redirect_transcribable_topic_query_params",
        user=request.user,
        topic=topic,
        project_slug=project_slug,
        item_id=item_id,
        asset_pk=asset_pk,
    )

    if not request.user.is_authenticated:
        user = get_anonymous_user()
    else:
        user = request.user

    asset = find_next_transcribable_topic_asset(topic, project_slug, item_id, asset_pk)
    structured_logger.info(
        "Redirecting to next transcribable asset in topic.",
        event_code="redirect_transcribable_topic_success",
        user=user,
        asset=asset,
        topic=topic,
    )
    return redirect_to_next_asset(asset, "transcribe", request, user)
