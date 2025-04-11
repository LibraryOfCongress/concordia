import json
import logging
import os
from smtplib import SMTPException
from time import time

from django.conf import settings
from django.contrib import messages
from django.core.mail import EmailMultiAlternatives, send_mail
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template import loader
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import FormView, ListView

from concordia.forms import ContactUsForm
from concordia.models import Banner, Campaign, CarouselSlide
from concordia.version import get_concordia_version

# The following are the imports needed to properly export views with __all__
from .accounts import (
    AccountDeletionView,
    AccountLetterView,
    AccountProfileView,
    ConcordiaLoginView,
    ConcordiaPasswordResetConfirmView,
    ConcordiaPasswordResetRequestView,
    ConcordiaRegistrationView,
    EmailReconfirmationView,
    get_pages,
)
from .ajax import (
    ajax_messages,
    ajax_session_status,
    generate_ocr_transcription,
    reserve_asset,
    review_transcription,
    rollback_transcription,
    rollforward_transcription,
    save_transcription,
    submit_tags,
    submit_transcription,
)
from .assets import (
    AssetDetailView,
    redirect_to_next_asset,
    redirect_to_next_reviewable_asset,
    redirect_to_next_reviewable_campaign_asset,
    redirect_to_next_reviewable_topic_asset,
    redirect_to_next_transcribable_asset,
    redirect_to_next_transcribable_campaign_asset,
    redirect_to_next_transcribable_topic_asset,
)
from .campaigns import (
    CampaignDetailView,
    CampaignListView,
    CampaignTopicListView,
    CompletedCampaignListView,
    FilteredCampaignDetailView,
    ReportCampaignView,
)
from .decorators import default_cache_control
from .items import FilteredItemDetailView, ItemDetailView
from .maintenance_mode import (
    maintenance_mode_frontend_available,
    maintenance_mode_frontend_unavailable,
    maintenance_mode_off,
    maintenance_mode_on,
)
from .projects import FilteredProjectDetailView, ProjectDetailView
from .rate_limit import ratelimit_view
from .simple_pages import (
    HelpCenterRedirectView,
    HelpCenterSpanishRedirectView,
    about_simple_page,
    simple_page,
)
from .topics import TopicDetailView

logger = logging.getLogger(__name__)


@never_cache
def healthz(request):
    status = {
        "current_time": time(),
        "load_average": os.getloadavg(),
        "debug": settings.DEBUG,
    }

    # We don't want to query a large table but we do want to hit the database
    # at last once:
    status["database_has_data"] = Campaign.objects.count() > 0

    status["application_version"] = get_concordia_version()

    return HttpResponse(content=json.dumps(status), content_type="application/json")


@method_decorator(default_cache_control, name="dispatch")
class HomeView(ListView):
    template_name = "home.html"

    queryset = (
        Campaign.objects.published()
        .listed()
        .filter(display_on_homepage=True)
        .order_by("ordering", "title")
    )
    context_object_name = "campaigns"

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data(*args, **kwargs)

        banner = Banner.objects.filter(active=True).first()

        if banner is not None:
            ctx["banner"] = banner

        ctx["slides"] = CarouselSlide.objects.published().order_by("ordering")

        if ctx["slides"]:
            ctx["firstslide"] = ctx["slides"][0]

        return ctx


@method_decorator(never_cache, name="dispatch")
class ContactUsView(FormView):
    template_name = "contact.html"
    form_class = ContactUsForm

    def get_context_data(self, *args, **kwargs):
        res = super().get_context_data(*args, **kwargs)
        res["title"] = "Contact Us"
        return res

    def get_initial(self):
        initial = super().get_initial()

        if (
            self.request.user.is_authenticated
            and self.request.user.username != "anonymous"
        ):
            initial["email"] = self.request.user.email

        initial["referrer"] = self.request.headers.get("Referer")

        return initial

    def form_valid(self, form):
        text_template = loader.get_template("emails/contact_us_email.txt")
        text_message = text_template.render(form.cleaned_data)

        html_template = loader.get_template("emails/contact_us_email.html")
        html_message = html_template.render(form.cleaned_data)

        confirmation_template = loader.get_template(
            "emails/contact_us_confirmation_email.txt"
        )
        confirmation_message = confirmation_template.render(form.cleaned_data)

        message = EmailMultiAlternatives(
            subject="Contact {}: {}".format(
                self.request.get_host(), form.cleaned_data["subject"]
            ),
            body=text_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.DEFAULT_TO_EMAIL],
            reply_to=[form.cleaned_data["email"]],
        )
        message.attach_alternative(html_message, "text/html")

        try:
            message.send()
            messages.success(self.request, "Your contact message has been sent.")
        except SMTPException:
            logger.exception(
                "Unable to send contact message to %s",
                settings.DEFAULT_TO_EMAIL,
                extra={"data": form.cleaned_data},
            )
            messages.error(
                self.request,
                "Your message could not be sent. Our support team has been notified.",
            )

        try:
            send_mail(
                "Contact {}: {}".format(
                    self.request.get_host(), form.cleaned_data["subject"]
                ),
                message=confirmation_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[form.cleaned_data["email"]],
            )
        except SMTPException:
            logger.exception(
                "Unable to send contact message to %s",
                form.cleaned_data["email"],
                extra={"data": form.cleaned_data},
            )

        return redirect("contact")


__all__ = [
    "healthz",
    "HomeView",
    "ContactUsView",
    "CampaignListView",
    "CompletedCampaignListView",
    "CampaignDetailView",
    "FilteredCampaignDetailView",
    "CampaignTopicListView",
    "ReportCampaignView",
    "ProjectDetailView",
    "FilteredProjectDetailView",
    "ItemDetailView",
    "FilteredItemDetailView",
    "AssetDetailView",
    "redirect_to_next_asset",
    "redirect_to_next_reviewable_asset",
    "redirect_to_next_transcribable_asset",
    "redirect_to_next_reviewable_campaign_asset",
    "redirect_to_next_transcribable_campaign_asset",
    "redirect_to_next_reviewable_topic_asset",
    "redirect_to_next_transcribable_topic_asset",
    "TopicDetailView",
    "simple_page",
    "about_simple_page",
    "HelpCenterRedirectView",
    "HelpCenterSpanishRedirectView",
    "ajax_session_status",
    "ajax_messages",
    "generate_ocr_transcription",
    "rollback_transcription",
    "rollforward_transcription",
    "save_transcription",
    "submit_transcription",
    "review_transcription",
    "submit_tags",
    "reserve_asset",
    "ConcordiaRegistrationView",
    "ConcordiaLoginView",
    "ConcordiaPasswordResetConfirmView",
    "ConcordiaPasswordResetRequestView",
    "EmailReconfirmationView",
    "AccountDeletionView",
    "AccountLetterView",
    "get_pages",
    "AccountProfileView",
    "ratelimit_view",
    "maintenance_mode_off",
    "maintenance_mode_on",
    "maintenance_mode_frontend_available",
    "maintenance_mode_frontend_unavailable",
]
