import datetime
import json
import os
import random
import re
import uuid
from functools import wraps
from logging import getLogger
from smtplib import SMTPException
from time import time
from urllib.parse import urlencode

import markdown
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (
    LoginView,
    PasswordResetConfirmView,
    PasswordResetView,
)
from django.contrib.messages import get_messages
from django.contrib.sites.shortcuts import get_current_site
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives, send_mail
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import (
    Case,
    Count,
    IntegerField,
    Max,
    Q,
    Subquery,
    Sum,
    When,
)
from django.db.models.functions import Greatest
from django.db.transaction import atomic
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template import Context, Template, loader
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.http import http_date
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import cache_control, cache_page, never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.decorators.vary import vary_on_headers
from django.views.generic import FormView, ListView, RedirectView, TemplateView
from django_ratelimit.decorators import ratelimit
from django_registration.backends.activation.views import RegistrationView
from maintenance_mode.core import set_maintenance_mode
from weasyprint import HTML

from concordia.api_views import APIDetailView, APIListView
from concordia.forms import (
    AccountDeletionForm,
    ActivateAndSetPasswordForm,
    AllowInactivePasswordResetForm,
    ContactUsForm,
    TurnstileForm,
    UserLoginForm,
    UserNameForm,
    UserProfileForm,
    UserRegistrationForm,
)
from concordia.models import (
    STATUS_COUNT_KEYS,
    Asset,
    AssetTranscriptionReservation,
    Banner,
    Campaign,
    CardFamily,
    CarouselSlide,
    ConcordiaUser,
    Guide,
    Item,
    Project,
    ResearchCenter,
    SimplePage,
    SiteReport,
    Tag,
    Topic,
    Transcription,
    TranscriptionStatus,
    TutorialCard,
    UserAssetTagCollection,
    UserProfileActivity,
)
from concordia.signals.signals import reservation_obtained, reservation_released
from concordia.templatetags.concordia_media_tags import asset_media_url
from concordia.utils import (
    get_anonymous_user,
    get_image_urls_from_asset,
    get_or_create_reservation_token,
    request_accepts_json,
)
from concordia.version import get_concordia_version

logger = getLogger(__name__)

ASSETS_PER_PAGE = 36
PROJECTS_PER_PAGE = 36
ITEMS_PER_PAGE = 36
URL_REGEX = r"http[s]?://"

MESSAGE_LEVEL_NAMES = dict(
    zip(
        messages.DEFAULT_LEVELS.values(),
        map(str.lower, messages.DEFAULT_LEVELS.keys()),
        strict=False,
    )
)


def default_cache_control(view_function):
    """
    Decorator for views which use our default cache control policy for public pages
    """

    @vary_on_headers("Accept-Encoding")
    @cache_control(public=True, max_age=settings.DEFAULT_PAGE_TTL)
    @wraps(view_function)
    def inner(*args, **kwargs):
        return view_function(*args, **kwargs)

    return inner


def user_cache_control(view_function):
    """
    Decorator for views that vary by user
    Only applicable if the user is authenticated
    """

    @vary_on_headers("Accept-Encoding", "Cookie")
    @cache_control(public=True, max_age=settings.DEFAULT_PAGE_TTL)
    @wraps(view_function)
    def inner(*args, **kwargs):
        return view_function(*args, **kwargs)

    return inner


def validate_anonymous_user(view):
    @wraps(view)
    @never_cache
    def inner(request, *args, **kwargs):
        if not request.user.is_authenticated and request.method == "POST":
            # First check if the user has already been validated within the time limit
            # If so, validation can be skipped
            turnstile_last_validated = request.session.get(
                "turnstile_last_validated", 0
            )
            age = time() - turnstile_last_validated
            if age > settings.ANONYMOUS_USER_VALIDATION_INTERVAL:
                form = TurnstileForm(request.POST)
                if not form.is_valid():
                    return JsonResponse(
                        {"error": "Unable to validate. " "Please try again or login."},
                        status=401,
                    )
                else:
                    # User has been validated, so we'll cache the time in their session
                    request.session["turnstile_last_validated"] = time()

        return view(request, *args, **kwargs)

    return inner


class AnonymousUserValidationCheckMixin:
    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)
        if not self.request.user.is_authenticated:
            turnstile_last_validated = self.request.session.get(
                "turnstile_last_validated", 0
            )
            age = time() - turnstile_last_validated
            context["anonymous_user_validation_required"] = (
                age > settings.ANONYMOUS_USER_VALIDATION_INTERVAL
            )
        else:
            context["anonymous_user_validation_required"] = False
        return context


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


@default_cache_control
def simple_page(request, path=None, slug=None, body_ctx=None):
    """
    Basic content management using Markdown managed in the SimplePage model

    This expects a pre-existing URL path matching the path specified in the database::

        path("about/", views.simple_page, name="about"),
    """

    if not path:
        path = request.path

    if body_ctx is None:
        body_ctx = {}

    page = get_object_or_404(SimplePage, path=path)

    md = markdown.Markdown(extensions=["meta"])

    breadcrumbs = []
    path_components = request.path.strip("/").split("/")
    for i, segment in enumerate(path_components[:-1], start=1):
        breadcrumbs.append(
            ("/%s/" % "/".join(path_components[0:i]), segment.replace("-", " ").title())
        )
    breadcrumbs.append((request.path, page.title))

    language_code = "en"
    if request.path.replace("/", "").endswith("-esp"):
        language_code = "es"

    ctx = {
        "language_code": language_code,
        "title": page.title,
        "breadcrumbs": breadcrumbs,
    }

    guide = page.guide_set.all().first()
    if guide is not None:
        html = "".join((page.body, guide.body))
        ctx["add_navigation"] = True
    else:
        html = page.body
    if "add_navigation" in ctx:
        ctx["guides"] = Guide.objects.order_by("order")
    body = Template(md.convert(html))
    ctx["body"] = body.render(Context(body_ctx))

    resp = render(request, "static-page.html", ctx)
    resp["Created"] = http_date(page.created_on.timestamp())
    resp["Last-Modified"] = http_date(page.updated_on.timestamp())
    return resp


@default_cache_control
def about_simple_page(request, path=None, slug=None):
    """
    Adds additional context to the "about" SimplePage
    """
    context_cache_key = "about_simple_page-about_context"
    about_context = cache.get(context_cache_key)
    if not about_context:
        try:
            active_campaigns = SiteReport.objects.filter(
                report_name=SiteReport.ReportName.TOTAL
            ).latest()
        except SiteReport.DoesNotExist:
            active_campaigns = SiteReport(
                campaigns_published=0,
                assets_published=0,
                assets_completed=0,
                assets_waiting_review=0,
                users_activated=0,
            )
        try:
            retired_campaigns = SiteReport.objects.filter(
                report_name=SiteReport.ReportName.RETIRED_TOTAL
            ).latest()
        except SiteReport.DoesNotExist:
            retired_campaigns = SiteReport(
                assets_published=0,
                assets_completed=0,
                assets_waiting_review=0,
            )
        about_context = {
            "report_date": now() - datetime.timedelta(days=1),
            "campaigns_published": active_campaigns.campaigns_published,
            "assets_published": active_campaigns.assets_published
            + retired_campaigns.assets_published,
            "assets_completed": active_campaigns.assets_completed
            + retired_campaigns.assets_completed,
            "assets_waiting_review": active_campaigns.assets_waiting_review
            + retired_campaigns.assets_waiting_review,
            "users_activated": active_campaigns.users_activated,
        }
        cache.set(context_cache_key, about_context, 60 * 60)

    return simple_page(request, path, slug, about_context)


@cache_control(private=True, max_age=settings.DEFAULT_PAGE_TTL)
@csrf_exempt
def ajax_session_status(request):
    """
    Returns the user-specific information which would otherwise make many pages
    uncacheable
    """

    user = request.user
    if user.is_anonymous:
        res = {}
    else:
        links = [
            {
                "title": "Profile",
                "url": request.build_absolute_uri(reverse("user-profile")),
            }
        ]
        if user.is_superuser or user.is_staff:
            links.append(
                {
                    "title": "Admin Area",
                    "url": request.build_absolute_uri(reverse("admin:index")),
                }
            )
        links.append(
            {
                "title": "Logout",
                "url": request.build_absolute_uri(reverse("logout")),
            }
        )

        res = {"username": user.username[:15], "links": links}

    return JsonResponse(res)


@never_cache
@login_required
@csrf_exempt
def ajax_messages(request):
    """
    Returns any messages queued for the current user
    """

    return JsonResponse(
        {
            "messages": [
                {"level": MESSAGE_LEVEL_NAMES[i.level], "message": i.message}
                for i in get_messages(request)
            ]
        }
    )


class ConcordiaPasswordResetConfirmView(PasswordResetConfirmView):
    # Automatically log a user in following a successful password reset
    post_reset_login = True
    form_class = ActivateAndSetPasswordForm


class ConcordiaPasswordResetRequestView(PasswordResetView):
    # Allow inactive users to reset their password and activate their account
    # in one step
    form_class = AllowInactivePasswordResetForm


def registration_rate(group, request):
    registration_form = UserRegistrationForm(request.POST)
    if registration_form.is_valid():
        return None
    else:
        return "10/h"


@method_decorator(never_cache, name="dispatch")
@method_decorator(
    ratelimit(
        group="registration",
        key="header:cf-connecting-ip",
        rate=registration_rate,
        method="POST",
        block=settings.RATELIMIT_BLOCK,
    ),
    name="post",
)
class ConcordiaRegistrationView(RegistrationView):
    form_class = UserRegistrationForm


@method_decorator(never_cache, name="dispatch")
class ConcordiaLoginView(LoginView):
    form_class = UserLoginForm

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            turnstile_form = TurnstileForm(request.POST)
            if turnstile_form.is_valid():
                return self.form_valid(form)
            else:
                form.add_error(
                    None, "Unable to validate. Please login or complete the challenge."
                )
                return self.form_invalid(form)

        else:
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        ctx["turnstile_form"] = TurnstileForm(auto_id=False)

        return ctx


def ratelimit_view(request, exception=None):
    status_code = 429

    ctx = {
        "error": "You have been rate-limited. Please try again later.",
        "status": status_code,
    }

    if exception is not None:
        ctx["exception"] = str(exception)

    if request.headers.get(
        "x-requested-with"
    ) == "XMLHttpRequest" or request_accepts_json(request):
        response = JsonResponse(ctx, status=status_code)
    else:
        response = render(request, "429.html", context=ctx, status=status_code)

    response["Retry-After"] = 15 * 60

    return response


@login_required
@never_cache
def AccountLetterView(request):
    # Generates a transcriptions and reviews contribution pdf letter
    # for the user and downloads it

    image_url = "file://{0}/{1}/img/logo.jpg".format(
        settings.SITE_ROOT_DIR, settings.STATIC_ROOT
    )
    user_profile_activity = UserProfileActivity.objects.filter(user=request.user)
    aggregate_sums = user_profile_activity.aggregate(
        Sum("review_count"), Sum("transcribe_count")
    )
    asset_list = _get_pages(request)
    context = {
        "user": request.user,
        "join_date": request.user.date_joined,
        "total_reviews": aggregate_sums["review_count__sum"],
        "total_transcriptions": aggregate_sums["transcribe_count__sum"],
        "image_url": image_url,
        "asset_list": asset_list,
    }
    template = loader.get_template("documents/service_letter.html")
    text = template.render(context)
    html = HTML(string=text)
    response = HttpResponse(
        content=html.write_pdf(variant="pdf/ua-1"), content_type="application/pdf"
    )
    response["Content-Disposition"] = "attachment; filename=letter.pdf"
    return response


def _get_pages(request):
    user = request.user
    activity = request.GET.get("activity", None)

    if activity == "transcribed":
        q = Q(user=user)
    elif activity == "reviewed":
        q = Q(reviewed_by=user)
    else:
        q = Q(user=user) | Q(reviewed_by=user)
    transcriptions = Transcription.objects.filter(q)

    assets = Asset.objects.filter(transcription__in=transcriptions)
    status_list = request.GET.getlist("status")
    if status_list and status_list != []:
        if "completed" not in status_list:
            assets = assets.exclude(transcription_status=TranscriptionStatus.COMPLETED)
        if "submitted" not in status_list:
            assets = assets.exclude(transcription_status=TranscriptionStatus.SUBMITTED)
        if "in_progress" not in status_list:
            assets = assets.exclude(
                transcription_status=TranscriptionStatus.IN_PROGRESS
            )

    assets = assets.select_related("item", "item__project", "item__project__campaign")

    assets = assets.annotate(
        last_transcribed=Max(
            "transcription__created_on",
            filter=Q(transcription__user=user),
        ),
        last_reviewed=Max(
            "transcription__updated_on",
            filter=Q(transcription__reviewed_by=user),
        ),
        latest_activity=Greatest(
            "last_transcribed",
            "last_reviewed",
            filter=Q(transcription__user=user) | Q(transcription__reviewed_by=user),
        ),
    )
    fmt = "%Y-%m-%d"
    start_date = None
    start = request.GET.get("start", None)
    if start is not None and len(start) > 0:
        start_date = timezone.make_aware(datetime.datetime.strptime(start, fmt))
    end_date = None
    end = request.GET.get("end", None)
    if end is not None and len(end) > 0:
        end_date = timezone.make_aware(datetime.datetime.strptime(end, fmt))
    if start_date is not None and end_date is not None:
        end_date += datetime.timedelta(days=1)
        end = end_date.strftime(fmt)
        assets = assets.filter(latest_activity__range=[start, end])
    elif start_date is not None or end_date is not None:
        date = start_date if start_date else end_date
        assets = assets.filter(
            latest_activity__year=date.year,
            latest_activity__month=date.month,
            latest_activity__day=date.day,
        )
    # CONCD-189 only show pages from the last 6 months
    # This should be an aware datetime, not a date. A date is cast
    # to a naive datetime when it's compared to a datetime
    # field, as is being done here
    SIX_MONTHS_AGO = now() - datetime.timedelta(days=6 * 30)
    assets = assets.filter(latest_activity__gte=SIX_MONTHS_AGO)
    order_by = request.GET.get("order_by", "date-descending")
    if order_by == "date-ascending":
        assets = assets.order_by("latest_activity", "-id")
    else:
        assets = assets.order_by("-latest_activity", "-id")

    campaign_id = request.GET.get("campaign", None)
    if campaign_id is not None:
        assets = assets.filter(item__project__campaign__pk=campaign_id)

    return assets


@login_required
@never_cache
def get_pages(request):
    asset_list = _get_pages(request)
    paginator = Paginator(asset_list, 30)  # Show 30 assets per page.

    page_number = int(request.GET.get("page", "1"))
    context = {
        "paginator": paginator,
        "page_obj": paginator.get_page(page_number),
        "is_paginated": True,
        "recent_campaigns": Campaign.objects.filter(project__item__asset__in=asset_list)
        .distinct()
        .order_by("title")
        .values("pk", "title"),
    }
    for param in ("activity", "end", "order_by", "start", "statuses"):
        context[param] = request.GET.get(param, None)
    campaign = request.GET.get("campaign", None)
    context["statuses"] = request.GET.getlist("status")

    if campaign is not None:
        context["campaign"] = Campaign.objects.get(pk=int(campaign))

    data = {}
    data["content"] = loader.render_to_string(
        "fragments/recent-pages.html", context, request=request
    )
    return JsonResponse(data)


@method_decorator(never_cache, name="dispatch")
class AccountProfileView(LoginRequiredMixin, FormView, ListView):
    template_name = "account/profile.html"
    form_class = UserProfileForm
    success_url = reverse_lazy("user-profile")
    reconfirmation_email_body_template = "emails/email_reconfirmation_body.txt"
    reconfirmation_email_subject_template = "emails/email_reconfirmation_subject.txt"

    # This view will list the assets which the user has contributed to
    # along with their most recent action on each asset. This will be
    # presented in the template as a standard paginated list of Asset
    # instances with annotations
    allow_empty = True
    paginate_by = 30

    def post(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()
        if "submit_name" in request.POST:
            form = UserNameForm(request.POST)
            if form.is_valid():
                user = ConcordiaUser.objects.get(id=request.user.id)
                user.first_name = form.cleaned_data["first_name"]
                user.last_name = form.cleaned_data["last_name"]
                user.save()
            return redirect("user-profile")
        else:
            return super().post(request, *args, **kwargs)

    def get_queryset(self):
        return _get_pages(self.request)

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data(*args, **kwargs)

        page = self.request.GET.get("page", None)
        campaign = self.request.GET.get("campaign", None)
        activity = self.request.GET.get("activity", None)
        status_list = self.request.GET.getlist("status")
        start = self.request.GET.get("start", None)
        end = self.request.GET.get("end", None)
        order_by = self.request.GET.get("order_by", None)
        if any([activity, campaign, page, status_list, start, end, order_by]):
            ctx["active_tab"] = "recent"
            if status_list:
                ctx["status_list"] = status_list
            ctx["order_by"] = self.request.GET.get("order_by", "date-descending")
        elif "active_tab" not in ctx:
            ctx["active_tab"] = self.request.GET.get("tab", "contributions")
        ctx["activity"] = activity
        if end is not None:
            ctx["end"] = end
        ctx["order_by"] = order_by
        if start is not None:
            ctx["start"] = start

        ctx["valid"] = self.request.session.pop("valid", None)

        user = self.request.user
        concordia_user = ConcordiaUser.objects.get(id=user.id)
        user_profile_activity = UserProfileActivity.objects.filter(user=user).order_by(
            "campaign__title"
        )
        ctx["user_profile_activity"] = user_profile_activity

        aggregate_sums = user_profile_activity.aggregate(
            Sum("review_count"), Sum("transcribe_count"), Sum("asset_count")
        )
        ctx["totalReviews"] = aggregate_sums["review_count__sum"]
        ctx["totalTranscriptions"] = aggregate_sums["transcribe_count__sum"]
        ctx["pages_worked_on"] = aggregate_sums["asset_count__sum"]
        if ctx["totalReviews"] is not None:
            ctx["totalCount"] = ctx["totalReviews"] + ctx["totalTranscriptions"]
        ctx["unconfirmed_email"] = concordia_user.get_email_for_reconfirmation()
        ctx["name_form"] = UserNameForm()
        return ctx

    def get_initial(self):
        initial = super().get_initial()
        initial["email"] = self.request.user.email
        return initial

    def get_form_kwargs(self):
        # We'll expose the request object to the form so we can validate that an
        # email is not in use:
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        user = self.request.user
        new_email = form.cleaned_data["email"]
        # This is annoying, but there's no better way to get the proxy model here
        # without being hacky (changing user.__class__ directly.)
        # Every method (such as using a user profile) would incur the same
        # database request.
        concordia_user = ConcordiaUser.objects.get(id=user.id)
        if settings.REQUIRE_EMAIL_RECONFIRMATION:
            concordia_user.set_email_for_reconfirmation(new_email)
            self.send_reconfirmation_email(concordia_user)
        else:
            concordia_user.email = new_email
            concordia_user.full_clean()
            concordia_user.save()
            concordia_user.delete_email_for_reconfirmation()

        self.request.session["valid"] = True

        return super().form_valid(form)

    def form_invalid(self, form):
        self.request.session["valid"] = False
        return self.render_to_response(
            self.get_context_data(form=form, active_tab="account")
        )

    def get_success_url(self):
        # automatically open the Account Settings tab
        return "{}#account".format(super().get_success_url())

    def get_reconfirmation_email_context(self, confirmation_key):
        return {
            "confirmation_key": confirmation_key,
            "expiration_days": settings.EMAIL_RECONFIRMATION_DAYS,
            "site": get_current_site(self.request),
        }

    def send_reconfirmation_email(self, user):
        confirmation_key = user.get_email_reconfirmation_key()
        context = self.get_reconfirmation_email_context(confirmation_key)
        context["user"] = user
        subject = render_to_string(
            template_name=self.reconfirmation_email_subject_template,
            context=context,
            request=self.request,
        )
        # Ensure subject is a single line
        subject = "".join(subject.splitlines())
        message = render_to_string(
            template_name=self.reconfirmation_email_body_template,
            context=context,
            request=self.request,
        )
        try:
            send_mail(
                subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.get_email_for_reconfirmation()],
            )
        except SMTPException:
            logger.exception(
                "Unable to send email reconfirmation to %s",
                user.get_email_for_reconfirmation(),
            )
            messages.error(
                self.request,
                _("Email confirmation could not be sent."),
            )


@method_decorator(never_cache, name="dispatch")
class AccountDeletionView(LoginRequiredMixin, FormView):
    template_name = "account/account_deletion.html"
    form_class = AccountDeletionForm
    success_url = reverse_lazy("homepage")
    email_body_template = "emails/delete_account_body.txt"
    email_subject_template = "emails/delete_account_subject.txt"

    def get_form_kwargs(self):
        # We expose the request object to the form so we can use it
        # to log the user out after deletion
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        self.delete_user(form.request.user, form.request)
        return super().form_valid(form)

    def delete_user(self, user, request):
        logger.info("Deletion request for %s", user)
        email = user.email
        if user.transcription_set.exists():
            logger.info("Anonymizing %s", user)
            user.username = "Anonymized %s" % uuid.uuid4()
            user.first_name = ""
            user.last_name = ""
            user.email = ""
            user.set_unusable_password()
            user.is_staff = False
            user.is_superuser = False
            user.is_active = False
            user.save()
        else:
            logger.info("Deleting %s", user)
            user.delete()
        self.send_deletion_email(email)
        logout(request)

    def send_deletion_email(self, email):
        context = {}
        subject = render_to_string(
            template_name=self.email_subject_template,
            context=context,
            request=self.request,
        )
        # Ensure subject is a single line
        subject = "".join(subject.splitlines())
        message = render_to_string(
            template_name=self.email_body_template,
            context=context,
            request=self.request,
        )
        try:
            send_mail(
                subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
            )
        except SMTPException:
            logger.exception(
                "Unable to send account deletion email to %s",
                email,
            )
            messages.error(
                self.request,
                _("Email confirmation of deletion could not be sent."),
            )


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


@method_decorator(default_cache_control, name="dispatch")
class CampaignListView(APIListView):
    template_name = "transcriptions/campaign_list.html"

    queryset = (
        Campaign.objects.published()
        .listed()
        .filter(status=Campaign.Status.ACTIVE)
        .order_by("ordering", "title")
    )
    context_object_name = "campaigns"

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data["topics"] = (
            Topic.objects.published().listed().order_by("ordering", "title")
        )
        data["completed_campaigns"] = (
            Campaign.objects.published()
            .listed()
            .filter(status__in=[Campaign.Status.COMPLETED, Campaign.Status.RETIRED])
            .order_by("ordering", "title")
        )
        return data

    def serialize_context(self, context):
        data = super().serialize_context(context)

        object_list = data["objects"]

        campaign_stats_qs = (
            Campaign.objects.filter(pk__in=[i["id"] for i in object_list])
            .annotate(
                **{
                    v: Count(
                        "project__item__asset",
                        filter=Q(
                            project__published=True,
                            project__item__published=True,
                            project__item__asset__published=True,
                            project__item__asset__transcription_status=k,
                        ),
                    )
                    for k, v in STATUS_COUNT_KEYS.items()
                }
            )
            .values("pk", *STATUS_COUNT_KEYS.values())
        )

        campaign_asset_counts = {}
        for campaign_stats in campaign_stats_qs:
            campaign_asset_counts[campaign_stats.pop("pk")] = campaign_stats

        for obj in object_list:
            obj["asset_stats"] = campaign_asset_counts[obj["id"]]

        return data


@method_decorator(default_cache_control, name="dispatch")
class CompletedCampaignListView(APIListView):
    model = Campaign
    template_name = "transcriptions/campaign_list_small_blocks.html"
    context_object_name = "campaigns"

    def _get_all_campaigns(self):
        campaignType = self.request.GET.get("type", None)
        campaigns = Campaign.objects.published().listed()
        if campaignType is None:
            return campaigns
        elif campaignType == "retired":
            status = Campaign.Status.RETIRED
        else:
            status = Campaign.Status.COMPLETED

        return campaigns.filter(status=status)

    def get_queryset(self):
        campaigns = self._get_all_campaigns()
        research_center = self.request.GET.get("research_center", None)
        if research_center is not None:
            campaigns = campaigns.filter(research_centers=research_center)
        return campaigns.order_by("-completed_date")

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data["research_centers"] = ResearchCenter.objects.filter(
            campaign__in=self._get_all_campaigns()
        ).distinct()

        return data


def calculate_asset_stats(asset_qs, ctx):
    asset_count = asset_qs.count()

    trans_qs = Transcription.objects.filter(asset__in=asset_qs).values_list(
        "user_id", "reviewed_by"
    )
    user_ids = set()
    for i, j in trans_qs.iterator():
        user_ids.add(i)
        user_ids.add(j)
    # Remove null values from the set, if it exists
    try:
        user_ids.remove(None)
    except KeyError:
        pass

    ctx["contributor_count"] = len(user_ids)

    asset_state_qs = asset_qs.values_list("transcription_status")
    asset_state_qs = asset_state_qs.annotate(Count("transcription_status")).order_by()
    status_counts_by_key = dict(asset_state_qs)

    ctx["transcription_status_counts"] = labeled_status_counts = []

    for status_key, status_label in TranscriptionStatus.CHOICES:
        value = status_counts_by_key.get(status_key, 0)
        if value:
            pct = round(100 * (value / asset_count))
        else:
            pct = 0

        ctx[f"{status_key}_percent"] = pct
        ctx[f"{status_key}_count"] = value
        labeled_status_counts.append((status_key, status_label, value))


def annotate_children_with_progress_stats(children):
    for obj in children:
        counts = {}

        for k, __ in TranscriptionStatus.CHOICES:
            counts[k] = getattr(obj, f"{k}_count", 0)

        obj.total_count = total = sum(counts.values())

        lowest_status = None

        for k, __ in TranscriptionStatus.CHOICES:
            count = counts[k]

            if total > 0:
                pct = round(100 * (count / total))
            else:
                pct = 0

            setattr(obj, f"{k}_percent", pct)

            if lowest_status is None and count > 0:
                lowest_status = k

        obj.lowest_transcription_status = lowest_status


@method_decorator(default_cache_control, name="dispatch")
class TopicListView(APIListView):
    template_name = "transcriptions/topic_list.html"
    paginate_by = 10
    queryset = Topic.objects.published().listed().order_by("ordering", "title")
    context_object_name = "topics"

    def serialize_context(self, context):
        data = super().serialize_context(context)

        object_list = data["objects"]

        topic_stats_qs = (
            Topic.objects.filter(pk__in=[i["id"] for i in object_list])
            .annotate(
                **{
                    v: Count(
                        "project__item__asset",
                        filter=Q(
                            project__published=True,
                            project__item__published=True,
                            project__item__asset__published=True,
                            project__item__asset__transcription_status=k,
                        ),
                    )
                    for k, v in STATUS_COUNT_KEYS.items()
                }
            )
            .values("pk", *STATUS_COUNT_KEYS.values())
        )

        topic_asset_counts = {}
        for topic_stats in topic_stats_qs:
            topic_asset_counts[topic_stats.pop("pk")] = topic_stats

        for obj in object_list:
            obj["asset_stats"] = topic_asset_counts[obj["id"]]

        return data


@method_decorator(default_cache_control, name="dispatch")
class CampaignTopicListView(TemplateView):
    template_name = "transcriptions/campaign_topic_list.html"

    def get(self, context):
        data = {}
        data["campaigns"] = (
            Campaign.objects.published()
            .listed()
            .filter(status=Campaign.Status.ACTIVE)
            .annotated()
            .order_by("ordering", "title")
        )
        data["topics"] = (
            Topic.objects.published().listed().order_by("ordering", "title")[:5]
        )
        data["completed_campaigns"] = (
            Campaign.objects.published()
            .listed()
            .filter(status__in=[Campaign.Status.COMPLETED, Campaign.Status.RETIRED])
            .order_by("ordering", "title")
        )

        return render(self.request, self.template_name, data)


@method_decorator(default_cache_control, name="dispatch")
@method_decorator(cache_page(60 * 60, cache="view_cache"), name="dispatch")
class TopicDetailView(APIDetailView):
    template_name = "transcriptions/topic_detail.html"
    context_object_name = "topic"
    queryset = Topic.objects.published().order_by("title")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        projects = (
            ctx["topic"]
            .project_set.published()
            .annotate(
                **{
                    f"{key}_count": Count(
                        "item__asset",
                        filter=Q(
                            item__published=True,
                            item__asset__published=True,
                            item__asset__transcription_status=key,
                        ),
                    )
                    for key in TranscriptionStatus.CHOICE_MAP.keys()
                }
            )
            .order_by("campaign", "ordering", "title")
        )

        ctx["filters"] = filters = {}
        status = self.request.GET.get("transcription_status")
        if status in TranscriptionStatus.CHOICE_MAP:
            projects = projects.exclude(**{f"{status}_count": 0})
            # We only want to pass specific QS parameters to lower-level search pages:
            filters["transcription_status"] = status
        ctx["sublevel_querystring"] = urlencode(filters)

        annotate_children_with_progress_stats(projects)
        ctx["projects"] = projects

        topic_assets = Asset.objects.filter(
            item__project__topics=self.object,
            item__project__published=True,
            item__published=True,
            published=True,
        )

        calculate_asset_stats(topic_assets, ctx)

        return ctx

    def serialize_context(self, context):
        ctx = super().serialize_context(context)
        ctx["object"]["related_links"] = [
            {"title": title, "url": url}
            for title, url, sequence in self.object.resource_set.values_list(
                "title", "resource_url"
            )
        ]
        return ctx


@method_decorator(default_cache_control, name="dispatch")
class CampaignDetailView(APIDetailView):
    template_name = "transcriptions/campaign_detail.html"
    completed_template_name = "transcriptions/campaign_detail_completed.html"
    retired_template_name = "transcriptions/campaign_detail_retired.html"
    context_object_name = "campaign"
    queryset = Campaign.objects.published().order_by("title")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.object and self.object.status == Campaign.Status.RETIRED:
            latest_report = SiteReport.objects.filter(campaign=ctx["campaign"]).latest(
                "created_on"
            )
            ctx["completed_count"] = latest_report.assets_completed
            ctx["contributor_count"] = latest_report.registered_contributors
        else:
            projects = (
                ctx["campaign"].project_set.published().order_by("ordering", "title")
            )
            ctx["filters"] = filters = {}
            filter_by_reviewable = kwargs.get("filter_by_reviewable", False)
            if filter_by_reviewable:
                projects = projects.filter(
                    item__asset__transcription__id__in=Transcription.objects.exclude(
                        user=self.request.user.id
                    ).values_list("id", flat=True)
                )
                ctx["filter_assets"] = True
            projects = projects.annotate(
                **{
                    f"{key}_count": Count(
                        "item__asset",
                        filter=Q(
                            item__published=True,
                            item__asset__published=True,
                            item__asset__transcription_status=key,
                        ),
                    )
                    for key in TranscriptionStatus.CHOICE_MAP
                }
            )

            if filter_by_reviewable:
                status = TranscriptionStatus.SUBMITTED
            else:
                status = self.request.GET.get("transcription_status")
            if status in TranscriptionStatus.CHOICE_MAP:
                projects = projects.exclude(**{f"{status}_count": 0})
                # We only want to pass specific QS parameters
                # to lower-level search pages:
                filters["transcription_status"] = status
            ctx["sublevel_querystring"] = urlencode(filters)

            annotate_children_with_progress_stats(projects)
            ctx["projects"] = projects

            campaign_assets = Asset.objects.filter(
                item__project__campaign=self.object,
                item__project__published=True,
                item__published=True,
                published=True,
            )
            if filter_by_reviewable:
                campaign_assets = campaign_assets.exclude(
                    transcription__user=self.request.user.id
                )
                ctx["transcription_status"] = TranscriptionStatus.SUBMITTED
            else:
                ctx["transcription_status"] = status

            calculate_asset_stats(campaign_assets, ctx)

        return ctx

    def serialize_context(self, context):
        ctx = super().serialize_context(context)
        ctx["object"]["related_links"] = [
            {"title": title, "url": url}
            for title, url in self.object.resource_set.values_list(
                "title", "resource_url"
            )
        ]
        return ctx

    def get_template_names(self):
        if self.object.status == Campaign.Status.COMPLETED:
            return [self.completed_template_name]
        elif self.object.status == Campaign.Status.RETIRED:
            return [self.retired_template_name]
        return super().get_template_names()


@method_decorator(user_cache_control, name="dispatch")
class FilteredCampaignDetailView(CampaignDetailView):
    def get_context_data(self, **kwargs):
        if self.request.user.is_authenticated and self.request.user.is_staff:
            kwargs["filter_by_reviewable"] = True

        return super().get_context_data(**kwargs)


@method_decorator(default_cache_control, name="dispatch")
class ProjectDetailView(APIListView):
    template_name = "transcriptions/project_detail.html"
    context_object_name = "items"
    paginate_by = 10

    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except Http404:
            campaign = get_object_or_404(
                Campaign.objects.published(), slug=self.kwargs["campaign_slug"]
            )
            return redirect(campaign)

    def get_queryset(self, filter_by_reviewable=False):
        self.project = get_object_or_404(
            Project.objects.published().select_related("campaign"),
            slug=self.kwargs["slug"],
            campaign__slug=self.kwargs["campaign_slug"],
        )

        item_qs = self.project.item_set.published().order_by("item_id")
        if filter_by_reviewable:
            item_qs = item_qs.exclude(asset__transcription__user=self.request.user.id)
        item_qs = item_qs.annotate(
            **{
                f"{key}_count": Count(
                    "asset", filter=Q(asset__transcription_status=key)
                )
                for key in TranscriptionStatus.CHOICE_MAP
            }
        )

        self.filters = {}

        if filter_by_reviewable:
            status = TranscriptionStatus.SUBMITTED
        else:
            status = self.request.GET.get("transcription_status")
        if status in TranscriptionStatus.CHOICE_MAP:
            item_qs = item_qs.exclude(**{f"{status}_count": 0})
            # We only want to pass specific QS parameters to lower-level search
            # pages so we'll record those here:
            self.filters["transcription_status"] = status

        return item_qs

    def get_context_data(self, **kws):
        ctx = super().get_context_data(**kws)
        ctx["project"] = project = self.project
        ctx["campaign"] = project.campaign

        if self.filters:
            ctx["sublevel_querystring"] = urlencode(self.filters)
            ctx["filters"] = self.filters

        project_assets = Asset.objects.filter(
            item__project=project, published=True, item__published=True
        )
        filter_by_reviewable = kws.get("filter_by_reviewable", False)
        if filter_by_reviewable:
            project_assets = project_assets.exclude(
                transcription__user=self.request.user.id
            )
            ctx["filter_assets"] = True
            ctx["transcription_status"] = TranscriptionStatus.SUBMITTED
        else:
            ctx["transcription_status"] = self.request.GET.get("transcription_status")

        calculate_asset_stats(project_assets, ctx)

        annotate_children_with_progress_stats(ctx["items"])

        return ctx

    def serialize_context(self, context):
        data = super().serialize_context(context)
        data["project"] = self.serialize_object(context["project"])
        return data


@method_decorator(user_cache_control, name="dispatch")
class FilteredProjectDetailView(ProjectDetailView):
    def get_queryset(self):
        return super().get_queryset(filter_by_reviewable=True)

    def get_context_data(self, **kws):
        kws["filter_by_reviewable"] = True

        return super().get_context_data(**kws)


@method_decorator(default_cache_control, name="dispatch")
class ItemDetailView(APIListView):
    """
    Handle GET requests on /campaign/<campaign>/<project>/<item>

    This uses a ListView to paginate the item's assets
    """

    template_name = "transcriptions/item_detail.html"
    context_object_name = "assets"
    paginate_by = 10

    http_method_names = ["get", "options", "head"]

    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except Http404:
            campaign = get_object_or_404(
                Campaign.objects.published(), slug=self.kwargs["campaign_slug"]
            )
            return redirect(campaign)

    def _get_assets(self):
        assets = self.item.asset_set.published()
        if self.kwargs.get("filter_by_reviewable", False):
            assets = assets.exclude(transcription__user=self.request.user.id)
        return assets

    def get_queryset(self):
        self.item = get_object_or_404(
            Item.objects.published().select_related("project__campaign"),
            project__campaign__slug=self.kwargs["campaign_slug"],
            project__slug=self.kwargs["project_slug"],
            item_id=self.kwargs["item_id"],
        )

        asset_qs = self._get_assets().order_by("sequence")
        asset_qs = asset_qs.select_related(
            "item__project__campaign", "item__project", "item"
        )

        self.filters = {}
        if self.kwargs.get("filter_by_reviewable", False):
            status = TranscriptionStatus.SUBMITTED
        else:
            status = self.request.GET.get("transcription_status")
        if status in TranscriptionStatus.CHOICE_MAP:
            asset_qs = asset_qs.filter(transcription_status=status)
            # We only want to pass specific QS parameters to lower-level search
            # pages so we'll record those here:
            self.filters["transcription_status"] = status

        return asset_qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        ctx.update(
            {
                "campaign": self.item.project.campaign,
                "project": self.item.project,
                "item": self.item,
                "sublevel_querystring": urlencode(self.filters),
                "filters": self.filters,
            }
        )

        item_assets = self._get_assets()
        if self.kwargs.get("filter_by_reviewable", False):
            ctx["filter_assets"] = True
            ctx["transcription_status"] = TranscriptionStatus.SUBMITTED
        else:
            ctx["transcription_status"] = self.request.GET.get("transcription_status")

        calculate_asset_stats(item_assets, ctx)

        return ctx

    def serialize_context(self, context):
        data = super().serialize_context(context)

        for i, asset in enumerate(context["object_list"]):
            serialized_asset = data["objects"][i]
            serialized_asset.pop("media_url")
            image_url, thumbnail_url = get_image_urls_from_asset(asset)
            serialized_asset["image_url"] = image_url
            serialized_asset["thumbnail_url"] = thumbnail_url

        data["item"] = self.serialize_object(context["item"])
        return data


@method_decorator(user_cache_control, name="dispatch")
class FilteredItemDetailView(ItemDetailView):
    def get_queryset(self):
        self.kwargs["filter_by_reviewable"] = True
        return super().get_queryset()

    def get_context_data(self, **kwargs):
        self.kwargs["filter_by_reviewable"] = True
        kwargs["filter_by_reviewable"] = True
        return super().get_context_data(**kwargs)


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


def get_transcription_superseded(asset, supersedes_pk):
    if not supersedes_pk:
        if asset.transcription_set.filter(supersedes=None).exists():
            return JsonResponse(
                {"error": "An open transcription already exists"}, status=409
            )
        else:
            superseded = None
    else:
        try:
            if asset.transcription_set.filter(supersedes=supersedes_pk).exists():
                return JsonResponse(
                    {"error": "This transcription has been superseded"}, status=409
                )

            try:
                superseded = asset.transcription_set.get(pk=supersedes_pk)
            except Transcription.DoesNotExist:
                return JsonResponse({"error": "Invalid supersedes value"}, status=400)
        except ValueError:
            return JsonResponse({"error": "Invalid supersedes value"}, status=400)
    return superseded


@require_POST
@login_required
@atomic
@ratelimit(key="header:cf-connecting-ip", rate="1/m", block=settings.RATELIMIT_BLOCK)
def generate_ocr_transcription(request, *, asset_pk):
    asset = get_object_or_404(Asset, pk=asset_pk)
    user = request.user

    supersedes_pk = request.POST.get("supersedes")
    language = request.POST.get("language", None)
    superseded = get_transcription_superseded(asset, supersedes_pk)
    if superseded:
        return superseded
    else:
        # This means this is the first transcription on this asset
        # to enable undoing of the OCR transcription, we create
        # an empty transcription for the OCR transcription to supersede
        superseded = Transcription(
            asset=asset,
            user=get_anonymous_user(),
            text="",
        )
        superseded.full_clean()
        superseded.save()

    transcription_text = asset.get_ocr_transcript(language)
    transcription = Transcription(
        asset=asset,
        user=user,
        supersedes=superseded,
        text=transcription_text,
        ocr_generated=True,
        ocr_originated=True,
    )
    transcription.full_clean()
    transcription.save()

    return JsonResponse(
        {
            "id": transcription.pk,
            "sent": time(),
            "submissionUrl": reverse("submit-transcription", args=(transcription.pk,)),
            "text": transcription.text,
            "asset": {
                "id": transcription.asset.id,
                "status": transcription.asset.transcription_status,
                "contributors": transcription.asset.get_contributor_count(),
            },
            "undo_available": asset.can_rollback()[0],
            "redo_available": asset.can_rollforward()[0],
        },
        status=201,
    )


@require_POST
@validate_anonymous_user
@atomic
@ratelimit(key="header:cf-connecting-ip", rate="1/m", block=settings.RATELIMIT_BLOCK)
def rollback_transcription(request, *, asset_pk):
    asset = get_object_or_404(Asset, pk=asset_pk)

    if request.user.is_anonymous:
        user = get_anonymous_user()
    else:
        user = request.user

    try:
        transcription = asset.rollback_transcription(user)
    except ValueError as e:
        logger.exception("No previous transcription available for rollback", exc_info=e)
        return JsonResponse(
            {"error": "No previous transcription available"}, status=400
        )

    return JsonResponse(
        {
            "id": transcription.pk,
            "sent": time(),
            "submissionUrl": reverse("submit-transcription", args=(transcription.pk,)),
            "text": transcription.text,
            "asset": {
                "id": transcription.asset.id,
                "status": transcription.asset.transcription_status,
                "contributors": transcription.asset.get_contributor_count(),
            },
            "message": "Successfully rolled back transcription to previous version",
            "undo_available": transcription.asset.can_rollback()[0],
            "redo_available": transcription.asset.can_rollforward()[0],
        },
        status=201,
    )


@require_POST
@validate_anonymous_user
@atomic
@ratelimit(key="header:cf-connecting-ip", rate="1/m", block=settings.RATELIMIT_BLOCK)
def rollforward_transcription(request, *, asset_pk):
    asset = get_object_or_404(Asset, pk=asset_pk)

    if request.user.is_anonymous:
        user = get_anonymous_user()
    else:
        user = request.user

    try:
        transcription = asset.rollforward_transcription(user)
    except ValueError as e:
        logger.exception("No transcription available for rollforward", exc_info=e)
        return JsonResponse({"error": "No transcription to restore"}, status=400)

    return JsonResponse(
        {
            "id": transcription.pk,
            "sent": time(),
            "submissionUrl": reverse("submit-transcription", args=(transcription.pk,)),
            "text": transcription.text,
            "asset": {
                "id": transcription.asset.id,
                "status": transcription.asset.transcription_status,
                "contributors": transcription.asset.get_contributor_count(),
            },
            "message": "Successfully restored transcription to next version",
            "undo_available": transcription.asset.can_rollback()[0],
            "redo_available": transcription.asset.can_rollforward()[0],
        },
        status=201,
    )


@require_POST
@validate_anonymous_user
@atomic
def save_transcription(request, *, asset_pk):
    asset = get_object_or_404(Asset, pk=asset_pk)
    logger.info("Saving transcription for %s (%s)", asset, asset.id)

    if request.user.is_anonymous:
        user = get_anonymous_user()
    else:
        user = request.user

    # Check whether this transcription text contains any URLs
    # If so, ask the user to correct the transcription by removing the URLs
    transcription_text = request.POST["text"]
    url_match = re.search(URL_REGEX, transcription_text)
    if url_match:
        return JsonResponse(
            {
                "error": "It looks like your text contains URLs. "
                "Please remove the URLs and try again."
            },
            status=400,
        )

    supersedes_pk = request.POST.get("supersedes")
    superseded = get_transcription_superseded(asset, supersedes_pk)
    if superseded and isinstance(superseded, HttpResponse):
        logger.info("Transcription superseded")
        return superseded

    if superseded and (superseded.ocr_generated or superseded.ocr_originated):
        ocr_originated = True
    else:
        ocr_originated = False

    transcription = Transcription(
        asset=asset,
        user=user,
        supersedes=superseded,
        text=transcription_text,
        ocr_originated=ocr_originated,
    )
    transcription.full_clean()
    transcription.save()
    logger.info("Transction %s saved", transcription.id)

    return JsonResponse(
        {
            "id": transcription.pk,
            "sent": time(),
            "submissionUrl": reverse("submit-transcription", args=(transcription.pk,)),
            "asset": {
                "id": transcription.asset.id,
                "status": transcription.asset.transcription_status,
                "contributors": transcription.asset.get_contributor_count(),
            },
            "undo_available": transcription.asset.can_rollback()[0],
            "redo_available": transcription.asset.can_rollforward()[0],
        },
        status=201,
    )


@require_POST
@validate_anonymous_user
def submit_transcription(request, *, pk):
    transcription = get_object_or_404(Transcription, pk=pk)
    asset = transcription.asset

    logger.info(
        "Transcription %s submitted for %s (%s)", transcription.id, asset, asset.id
    )

    is_superseded = transcription.asset.transcription_set.filter(supersedes=pk).exists()
    is_already_submitted = transcription.submitted and not transcription.rejected

    if is_already_submitted or is_superseded:
        logger.warning(
            (
                "Submit for review was attempted for invalid transcription "
                "record: submitted: %s pk: %d"
            ),
            str(transcription.submitted),
            pk,
        )
        return JsonResponse(
            {
                "error": "This transcription has already been updated."
                " Reload the current status before continuing."
            },
            status=400,
        )

    transcription.submitted = now()
    transcription.rejected = None
    transcription.full_clean()
    transcription.save()

    logger.info("Transcription %s successfully submitted", transcription.id)

    return JsonResponse(
        {
            "id": transcription.pk,
            "sent": time(),
            "asset": {
                "id": transcription.asset.id,
                "status": transcription.asset.transcription_status,
                "contributors": transcription.asset.get_contributor_count(),
            },
            "undo_available": False,
            "redo_available": False,
        },
        status=200,
    )


@require_POST
@login_required
@never_cache
def review_transcription(request, *, pk):
    action = request.POST.get("action")

    if action not in ("accept", "reject"):
        return JsonResponse({"error": "Invalid action"}, status=400)

    transcription = get_object_or_404(Transcription, pk=pk)
    asset = transcription.asset

    logger.info(
        "Transcription %s reviewed (%s) for %s (%s)",
        transcription.id,
        action,
        asset,
        asset.id,
    )

    if transcription.accepted or transcription.rejected:
        return JsonResponse(
            {"error": "This transcription has already been reviewed"}, status=400
        )

    if transcription.user.pk == request.user.pk and action == "accept":
        logger.warning("Attempted self-acceptance for transcription %s", transcription)
        return JsonResponse(
            {"error": "You cannot accept your own transcription"}, status=400
        )

    transcription.reviewed_by = request.user

    if action == "accept":
        transcription.accepted = now()
    else:
        transcription.rejected = now()

    transcription.full_clean()
    transcription.save()

    logger.info("Transcription %s successfully reviewed (%s)", transcription.id, action)

    return JsonResponse(
        {
            "id": transcription.pk,
            "sent": time(),
            "asset": {
                "id": transcription.asset.id,
                "status": transcription.asset.transcription_status,
                "contributors": transcription.asset.get_contributor_count(),
            },
        },
        status=200,
    )


@require_POST
@login_required
@atomic
def submit_tags(request, *, asset_pk):
    asset = get_object_or_404(Asset, pk=asset_pk)

    user_tags, created = UserAssetTagCollection.objects.get_or_create(
        asset=asset, user=request.user
    )

    tags = set(request.POST.getlist("tags"))
    existing_tags = Tag.objects.filter(value__in=tags)
    new_tag_values = tags.difference(i.value for i in existing_tags)
    new_tags = [Tag(value=i) for i in new_tag_values]
    try:
        for i in new_tags:
            i.full_clean()
    except ValidationError as exc:
        return JsonResponse({"error": exc.messages}, status=400)

    Tag.objects.bulk_create(new_tags)

    # At this point we now have Tag objects for everything in the POSTed
    # request. We'll add anything which wasn't previously in this user's tag
    # collection and remove anything which is no longer present.

    all_submitted_tags = list(existing_tags) + new_tags

    existing_user_tags = user_tags.tags.all()

    for tag in all_submitted_tags:
        if tag not in existing_user_tags:
            user_tags.tags.add(tag)

    all_tags_qs = Tag.objects.filter(userassettagcollection__asset__pk=asset_pk)

    for tag in all_tags_qs:
        if tag not in all_submitted_tags:
            for collection in asset.userassettagcollection_set.all():
                collection.tags.remove(tag)

    all_tags = all_tags_qs.order_by("value")

    final_user_tags = user_tags.tags.order_by("value").values_list("value", flat=True)
    all_tags = all_tags.values_list("value", flat=True).distinct()

    return JsonResponse(
        {"user_tags": list(final_user_tags), "all_tags": list(all_tags)}
    )


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


@method_decorator(default_cache_control, name="dispatch")
class ReportCampaignView(TemplateView):
    """
    Report about campaign resources and status
    """

    template_name = "transcriptions/campaign_report.html"

    def get(self, request, campaign_slug):
        campaign = get_object_or_404(Campaign.objects.published(), slug=campaign_slug)

        try:
            page = int(self.request.GET.get("page", "1"))
        except ValueError:
            page = 1

        campaign_assets = Asset.objects.published().filter(
            item__project__campaign=campaign
        )

        ctx = {
            "title": campaign.title,
            "campaign_slug": campaign.slug,
            "total_asset_count": campaign_assets.count(),
        }

        projects_qs = campaign.project_set.published().order_by("title")

        projects_qs = projects_qs.annotate(
            asset_count=Count(
                "item__asset",
                filter=Q(item__published=True, item__asset__published=True),
                distinct=True,
            )
        )
        projects_qs = projects_qs.annotate(
            tag_count=Count("item__asset__userassettagcollection__tags", distinct=True)
        )
        projects_qs = projects_qs.annotate(
            transcriber_count=Count("item__asset__transcription__user", distinct=True),
            reviewer_count=Count(
                "item__asset__transcription__reviewed_by", distinct=True
            ),
        )

        paginator = Paginator(projects_qs, ASSETS_PER_PAGE)
        if page > paginator.num_pages:
            page = 1
        projects_page = paginator.get_page(page)

        self.add_transcription_status_summary_to_projects(projects_page)

        ctx["paginator"] = paginator
        ctx["projects"] = projects_page

        return render(self.request, self.template_name, ctx)

    def add_transcription_status_summary_to_projects(self, projects):
        status_qs = Asset.objects.filter(
            item__published=True, item__project__in=projects, published=True
        )
        status_qs = status_qs.values_list("item__project__id", "transcription_status")
        status_qs = status_qs.annotate(Count("transcription_status"))
        project_statuses = {}

        for project_id, status_value, count in status_qs:
            status_name = TranscriptionStatus.CHOICE_MAP[status_value]
            project_statuses.setdefault(project_id, []).append((status_name, count))

        # We'll sort the statuses in the same order they're presented in the choices
        # list so the display order will be both stable and consistent with the way
        # we talk about the workflow:
        sort_order = [j for i, j in TranscriptionStatus.CHOICES]

        for project in projects:
            statuses = project_statuses.get(project.id, [])
            statuses.sort(key=lambda i: sort_order.index(i[0]))
            project.transcription_statuses = statuses


def reserve_rate(group, request):
    # `group` is the group of rate limits to count together
    # It defaults to the dotted name of the view, so each
    # view is its own unique group
    return None if request.user.is_authenticated else "100/m"


@ratelimit(
    key="header:cf-connecting-ip", rate=reserve_rate, block=settings.RATELIMIT_BLOCK
)
@require_POST
@never_cache
def reserve_asset(request, *, asset_pk):
    """
    Receives an asset PK and attempts to create/update a reservation for it

    Returns JSON message with reservation token on success

    Returns HTTP 409 when the record is in use
    """

    reservation_token = get_or_create_reservation_token(request)

    # If the browser is letting us know of a specific reservation release,
    # let it go even if it's within the grace period.
    if request.POST.get("release"):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM concordia_assettranscriptionreservation
                WHERE asset_id = %s and reservation_token = %s
                """,
                [asset_pk, reservation_token],
            )

        # We'll pass the message to the WebSocket listeners before returning it:
        msg = {"asset_pk": asset_pk, "reservation_token": reservation_token}
        logger.info("Releasing reservation with token %s", reservation_token)
        reservation_released.send(sender="reserve_asset", **msg)
        return JsonResponse(msg)

    # We're relying on the database to meet our integrity requirements and since
    # this is called periodically we want to be fairly fast until we switch to
    # something like Redis.

    reservations = AssetTranscriptionReservation.objects.filter(
        asset_id__exact=asset_pk
    )

    # Default: pretend there is no activity on the asset
    is_it_already_mine = False
    am_i_tombstoned = False
    is_someone_else_tombstoned = False
    is_someone_else_active = False

    if reservations:
        for reservation in reservations:
            if reservation.tombstoned:
                if reservation.reservation_token == reservation_token:
                    am_i_tombstoned = True
                    logger.debug("I'm tombstoned %s", reservation_token)
                else:
                    is_someone_else_tombstoned = True
                    logger.debug(
                        "Someone else is tombstoned %s", reservation.reservation_token
                    )
            else:
                if reservation.reservation_token == reservation_token:
                    is_it_already_mine = True
                    logger.debug(
                        "I already have this active reservation %s", reservation_token
                    )
                if not is_it_already_mine:
                    is_someone_else_active = True
                    logger.info(
                        "Someone else has this active reservation %s",
                        reservation.reservation_token,
                    )

        if am_i_tombstoned:
            return HttpResponse(status=408)  # Request Timed Out

        if is_someone_else_active:
            return HttpResponse(status=409)  # Conflict

        if is_it_already_mine:
            # This user already has the reservation and it's not tombstoned
            msg = update_reservation(asset_pk, reservation_token)
            logger.debug("Updating reservation %s", reservation_token)

        if is_someone_else_tombstoned:
            msg = obtain_reservation(asset_pk, reservation_token)
            logger.debug(
                "Obtaining reservation for %s from tombstoned user", reservation_token
            )

    else:
        # No reservations = no activity = go ahead and do an insert
        msg = obtain_reservation(asset_pk, reservation_token)
        logger.debug("No activity, just get the reservation %s", reservation_token)

    return JsonResponse(msg)


def update_reservation(asset_pk, reservation_token):
    with connection.cursor() as cursor:
        cursor.execute(
            """
        UPDATE concordia_assettranscriptionreservation AS atr
            SET updated_on = current_timestamp
            WHERE (
                atr.asset_id = %s
                AND atr.reservation_token = %s
                AND atr.tombstoned != TRUE
                )
        """.strip(),
            [asset_pk, reservation_token],
        )
    # We'll pass the message to the WebSocket listeners before returning it:
    msg = {"asset_pk": asset_pk, "reservation_token": reservation_token}
    reservation_obtained.send(sender="reserve_asset", **msg)
    return msg


def obtain_reservation(asset_pk, reservation_token):
    with connection.cursor() as cursor:
        cursor.execute(
            """
        INSERT INTO concordia_assettranscriptionreservation AS atr
            (asset_id, reservation_token, tombstoned, created_on,
            updated_on)
            VALUES (%s, %s, FALSE, current_timestamp,
            current_timestamp)
        """.strip(),
            [asset_pk, reservation_token],
        )
    # We'll pass the message to the WebSocket listeners before returning it:
    msg = {"asset_pk": asset_pk, "reservation_token": reservation_token}
    reservation_obtained.send(sender="reserve_asset", **msg)
    return msg


def redirect_to_next_asset(potential_assets, mode, request, project_slug, user):
    asset = potential_assets.first()
    reservation_token = get_or_create_reservation_token(request)
    if asset:
        if mode == "transcribe":
            res = AssetTranscriptionReservation(
                asset=asset, reservation_token=reservation_token
            )
            res.full_clean()
            res.save()
        return redirect(
            "transcriptions:asset-detail",
            asset.item.project.campaign.slug,
            asset.item.project.slug,
            asset.item.item_id,
            asset.slug,
        )
    else:
        no_pages_message = "There are no remaining pages to %s in this project"

        messages.info(request, no_pages_message % mode)

        return redirect("homepage")


def filter_and_order_transcribable_assets(
    potential_assets, project_slug, item_id, asset_id
):
    potential_assets = potential_assets.filter(
        Q(transcription_status=TranscriptionStatus.NOT_STARTED)
        | Q(transcription_status=TranscriptionStatus.IN_PROGRESS)
    )

    potential_assets = potential_assets.exclude(
        pk__in=Subquery(AssetTranscriptionReservation.objects.values("asset_id"))
    )
    potential_assets = potential_assets.select_related("item", "item__project")

    # We'll favor assets which are in the same item or project as the original:
    potential_assets = potential_assets.annotate(
        unstarted=Case(
            When(transcription_status=TranscriptionStatus.NOT_STARTED, then=1),
            default=0,
            output_field=IntegerField(),
        ),
        same_project=Case(
            When(item__project__slug=project_slug, then=1),
            default=0,
            output_field=IntegerField(),
        ),
        same_item=Case(
            When(item__item_id=item_id, then=1), default=0, output_field=IntegerField()
        ),
        next_asset=Case(
            When(pk__gt=asset_id, then=1), default=0, output_field=IntegerField()
        ),
    ).order_by("-next_asset", "-unstarted", "-same_project", "-same_item", "sequence")

    return potential_assets


def filter_and_order_reviewable_assets(
    potential_assets, project_slug, item_id, asset_id, user_pk
):
    potential_assets = potential_assets.filter(
        transcription_status=TranscriptionStatus.SUBMITTED
    )
    potential_assets = potential_assets.exclude(transcription__user=user_pk)
    potential_assets = potential_assets.exclude(
        pk__in=Subquery(AssetTranscriptionReservation.objects.values("asset_id"))
    )
    potential_assets = potential_assets.select_related("item", "item__project")

    # We'll favor assets which are in the same item or project as the original:
    potential_assets = potential_assets.annotate(
        same_project=Case(
            When(item__project__slug=project_slug, then=1),
            default=0,
            output_field=IntegerField(),
        ),
        same_item=Case(
            When(item__item_id=item_id, then=1), default=0, output_field=IntegerField()
        ),
        next_asset=Case(
            When(pk__gt=asset_id, then=1), default=0, output_field=IntegerField()
        ),
    ).order_by("-next_asset", "-same_project", "-same_item", "sequence")

    return potential_assets


def find_reviewable_asset(campaign, user):
    return (
        Asset.objects.select_for_update(skip_locked=True, of=("self",))
        .exclude(transcription__user=user.pk)
        .filter(
            campaign=campaign,
            published=True,
            transcription_status=TranscriptionStatus.SUBMITTED,
        )
        .exclude(
            pk__in=Subquery(AssetTranscriptionReservation.objects.values("asset_id"))
        )
        .select_related("item", "item__project")
        .order_by("sequence")
        .first()
    )


@never_cache
@atomic
def redirect_to_next_reviewable_asset(request):
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
        asset = find_reviewable_asset(campaign, user)
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
            asset = find_reviewable_asset(campaign, user)
            if asset:
                break
            else:
                logger.info("No reviewable assets found in %s", campaign)

    if asset:
        return redirect(
            "transcriptions:asset-detail",
            asset.item.project.campaign.slug,
            asset.item.project.slug,
            asset.item.item_id,
            asset.slug,
        )
    else:
        messages.info(request, "There are no remaining pages to review")

        return redirect("homepage")


def find_transcribable_asset(campaign):
    return (
        Asset.objects.select_for_update(skip_locked=True, of=("self",))
        .filter(
            campaign=campaign,
            published=True,
            transcription_status=TranscriptionStatus.NOT_STARTED,
        )
        .exclude(
            pk__in=Subquery(AssetTranscriptionReservation.objects.values("asset_id"))
        )
        .select_related("item", "item__project")
        .order_by("sequence")
        .first()
    )


@never_cache
@atomic
def redirect_to_next_transcribable_asset(request):
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
        logger.info("No configured reviewable campaigns")

    for campaign_id in campaign_ids:
        try:
            campaign = Campaign.objects.get(id=campaign_id)
        except IndexError:
            logger.error("Next transcribable campaign %s not found", campaign_id)
            continue
        asset = find_transcribable_asset(campaign)
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
            asset = find_transcribable_asset(campaign)
            if asset:
                break
            else:
                logger.info("No transcribable assets found in %s", campaign)

    if asset:
        reservation_token = get_or_create_reservation_token(request)
        res = AssetTranscriptionReservation(
            asset=asset, reservation_token=reservation_token
        )
        res.full_clean()
        res.save()
        return redirect(
            "transcriptions:asset-detail",
            asset.item.project.campaign.slug,
            asset.item.project.slug,
            asset.item.item_id,
            asset.slug,
        )
    else:
        messages.info(request, "There are no remaining pages to transcribe")

        return redirect("homepage")


@never_cache
@atomic
def redirect_to_next_reviewable_campaign_asset(request, *, campaign_slug):
    # Campaign is specified: may be listed or unlisted
    campaign = get_object_or_404(Campaign.objects.published(), slug=campaign_slug)
    project_slug = request.GET.get("project", "")
    item_id = request.GET.get("item", "")
    asset_id = request.GET.get("asset", 0)

    if not request.user.is_authenticated:
        user = get_anonymous_user()
    else:
        user = request.user

    potential_assets = Asset.objects.select_for_update(skip_locked=True, of=("self",))
    potential_assets = potential_assets.filter(
        item__project__campaign=campaign,
        item__project__published=True,
        item__published=True,
        published=True,
    )

    potential_assets = filter_and_order_reviewable_assets(
        potential_assets, project_slug, item_id, asset_id, request.user.pk
    )

    return redirect_to_next_asset(
        potential_assets, "review", request, project_slug, user
    )


@never_cache
@atomic
def redirect_to_next_transcribable_campaign_asset(request, *, campaign_slug):
    # Campaign is specified: may be listed or unlisted
    campaign = get_object_or_404(Campaign.objects.published(), slug=campaign_slug)
    project_slug = request.GET.get("project", "")
    item_id = request.GET.get("item", "")
    asset_id = request.GET.get("asset", 0)

    if not request.user.is_authenticated:
        user = get_anonymous_user()
    else:
        user = request.user

    potential_assets = Asset.objects.select_for_update(skip_locked=True, of=("self",))
    potential_assets = potential_assets.filter(
        item__project__campaign=campaign,
        item__project__published=True,
        item__published=True,
        published=True,
    )
    potential_assets = filter_and_order_transcribable_assets(
        potential_assets, project_slug, item_id, asset_id
    )

    return redirect_to_next_asset(
        potential_assets, "transcribe", request, project_slug, user
    )


@never_cache
@atomic
def redirect_to_next_reviewable_topic_asset(request, *, topic_slug):
    # Topic is specified: may be listed or unlisted
    topic = get_object_or_404(Topic.objects.published(), slug=topic_slug)
    project_slug = request.GET.get("project", "")
    item_id = request.GET.get("item", "")
    asset_id = request.GET.get("asset", 0)

    if not request.user.is_authenticated:
        user = get_anonymous_user()
    else:
        user = request.user

    potential_assets = Asset.objects.select_for_update(skip_locked=True, of=("self",))
    potential_assets = potential_assets.filter(
        item__project__topics__in=(topic,),
        item__project__published=True,
        item__published=True,
        published=True,
    )

    potential_assets = filter_and_order_reviewable_assets(
        potential_assets, project_slug, item_id, asset_id, request.user.pk
    )

    return redirect_to_next_asset(
        potential_assets, "review", request, project_slug, user
    )


@never_cache
@atomic
def redirect_to_next_transcribable_topic_asset(request, *, topic_slug):
    # Topic is specified: may be listed or unlisted
    topic = get_object_or_404(Topic.objects.published(), slug=topic_slug)
    project_slug = request.GET.get("project", "")
    item_id = request.GET.get("item", "")
    asset_id = request.GET.get("asset", 0)

    if not request.user.is_authenticated:
        user = get_anonymous_user()
    else:
        user = request.user

    potential_assets = Asset.objects.select_for_update(skip_locked=True, of=("self",))
    potential_assets = potential_assets.filter(
        item__project__topics__in=(topic,),
        item__project__published=True,
        item__published=True,
        published=True,
    )

    potential_assets = filter_and_order_transcribable_assets(
        potential_assets, project_slug, item_id, asset_id
    )

    return redirect_to_next_asset(
        potential_assets, "transcribe", request, project_slug, user
    )


class EmailReconfirmationView(TemplateView):
    success_url = reverse_lazy("user-profile")
    template_name = "account/email_reconfirmation_failed.html"

    BAD_USERNAME_MESSAGE = _("The account you attempted to confirm is invalid.")
    BAD_EMAIL_MESSAGE = _("The email you attempted to confirm is invalid.")
    EXPIRED_MESSAGE = _(
        "The confirmation key you provided is expired. Email confirmation links "
        "expire after 7 days. If your key is expired, you will need to re-enter "
        "your new email address"
    )
    INVALID_KEY_MESSAGE = _(
        "The confirmation key you provided is invalid. Email confirmation links "
        "expire after 7 days. If your key is expired, you will need to re-enter "
        "your new email address."
    )

    def get_success_url(self):
        return "{}#account".format(self.success_url)

    def get(self, *args, **kwargs):
        extra_context = {}
        try:
            self.confirm(*args, **kwargs)
        except ValidationError as exc:
            extra_context["reconfirmation_error"] = {
                "message": exc.message,
                "code": exc.code,
                "params": exc.params,
            }
            context_data = self.get_context_data()
            context_data.update(extra_context)
            return self.render_to_response(context_data, status=403)
        else:
            return HttpResponseRedirect(self.get_success_url())

    def confirm(self, *args, **kwargs):
        username, email = self.validate_key(kwargs.get("confirmation_key"))
        user = self.get_user(username)
        if not user.validate_reconfirmation_email(email):
            raise ValidationError(self.BAD_EMAIL_MESSAGE, code="bad_email") from None
        try:
            user.email = email
            user.full_clean()
        except ValidationError:
            raise ValidationError(self.BAD_EMAIL_MESSAGE, code="bad_email") from None
        user.save()
        user.delete_email_for_reconfirmation()
        return user

    def validate_key(self, confirmation_key):
        try:
            context = signing.loads(
                confirmation_key, max_age=settings.EMAIL_RECONFIRMATION_TIMEOUT
            )
            return context["username"], context["email"]
        except signing.SignatureExpired as exc:
            raise ValidationError(self.EXPIRED_MESSAGE, code="expired") from exc
        except signing.BadSignature as exc:
            raise ValidationError(
                self.INVALID_KEY_MESSAGE,
                code="invalid_key",
                params={"confirmation_key": confirmation_key},
            ) from exc

    def get_user(self, username):
        try:
            user = ConcordiaUser.objects.get(username=username)
            return user
        except ConcordiaUser.DoesNotExist as exc:
            raise ValidationError(
                self.BAD_USERNAME_MESSAGE, code="bad_username"
            ) from exc


# These views are to make sure various links to help-center URLs don't break
# when the URLs are changed to not include help-center and can be removed after
# all links are updated.


class HelpCenterRedirectView(RedirectView):
    def get_redirect_url(self, *args, **kwargs):
        path = kwargs["page_slug"]
        return "/get-started/" + path + "/"


class HelpCenterSpanishRedirectView(RedirectView):
    def get_redirect_url(self, *args, **kwargs):
        path = kwargs["page_slug"]
        return "/get-started-esp/" + path + "-esp/"


# End of help-center views

# Maintenance mode views


def maintenance_mode_off(request):
    """
    Deactivate maintenance-mode and redirect to site root.
    Only superusers are allowed to use this view.
    """
    if request.user.is_superuser:
        set_maintenance_mode(False)

    # Added cache busting to make sure maintenance mode banner is
    # always displayed/removed
    return HttpResponseRedirect("/?t={}".format(int(time())))


def maintenance_mode_on(request):
    """
    Activate maintenance-mode and redirect to site root.
    Only superusers are allowed to use this view.
    """
    if request.user.is_superuser:
        set_maintenance_mode(True)

    # Added cache busting to make sure maintenance mode banner is
    # always displayed/removed
    return HttpResponseRedirect("/?t={}".format(int(time())))


def maintenance_mode_frontend_available(request):
    """
    Allow staff and superusers to use the front-end
    while maintenance mode is active
    Only superusers are allowed to use this view.
    """
    if request.user.is_superuser:
        cache.set("maintenance_mode_frontend_available", True, None)

    return HttpResponseRedirect("/?t={}".format(int(time())))


def maintenance_mode_frontend_unavailable(request):
    """
    Disallow all use of the front-end while maintenance
    mode is active
    Only superusers are allowed to use this view.
    """
    if request.user.is_superuser:
        cache.set("maintenance_mode_frontend_available", False, None)

    return HttpResponseRedirect("/?t={}".format(int(time())))


# End of maintenance mode views
