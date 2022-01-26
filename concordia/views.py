import json
import os
import re
import datetime
from fpdf import FPDF
from functools import wraps
from logging import getLogger
from operator import attrgetter
from smtplib import SMTPException
from time import time
from urllib.parse import urlencode
import markdown
from captcha.fields import CaptchaField
from captcha.helpers import captcha_image_url
from captcha.models import CaptchaStore
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (
    LoginView,
    PasswordResetConfirmView,
    PasswordResetView,
)
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives, send_mail
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Case, Count, IntegerField, Max, OuterRef, Q, Subquery, When
from django.db.transaction import atomic
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template import loader
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.http import http_date
from django.utils.timezone import now
from django.views.decorators.cache import cache_control, never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.decorators.vary import vary_on_headers
from django.views.generic import FormView, ListView, TemplateView
from django_registration.backends.activation.views import RegistrationView
from flags.decorators import flag_required
from ratelimit.decorators import ratelimit
from ratelimit.mixins import RatelimitMixin
from ratelimit.utils import is_ratelimited
from concordia.api_views import APIDetailView, APIListView
from concordia.forms import (
    ActivateAndSetPasswordForm,
    AllowInactivePasswordResetForm,
    ContactUsForm,
    UserLoginForm,
    UserProfileForm,
    UserRegistrationForm,
)
from concordia.models import (
    Asset,
    AssetTranscriptionReservation,
    Campaign,
    CarouselSlide,
    Item,
    Project,
    SimplePage,
    Tag,
    Topic,
    Transcription,
    TranscriptionStatus,
    UserAssetTagCollection,
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
        messages.DEFAULT_LEVELS.values(), map(str.lower, messages.DEFAULT_LEVELS.keys())
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
def simple_page(request, path=None):
    """
    Basic content management using Markdown managed in the SimplePage model

    This expects a pre-existing URL path matching the path specified in the database::

        path("about/", views.simple_page, name="about"),
    """

    if not path:
        path = request.path

    page = get_object_or_404(SimplePage, path=path)

    md = markdown.Markdown(extensions=["meta"])
    html = md.convert(page.body)

    breadcrumbs = []
    path_components = request.path.strip("/").split("/")
    for i, segment in enumerate(path_components[:-1], start=1):
        breadcrumbs.append(
            ("/%s/" % "/".join(path_components[0:i]), segment.replace("-", " ").title())
        )
    breadcrumbs.append((request.path, page.title))

    ctx = {"body": html, "title": page.title, "breadcrumbs": breadcrumbs}

    resp = render(request, "static-page.html", ctx)
    resp["Created"] = http_date(page.created_on.timestamp())
    resp["Last-Modified"] = http_date(page.updated_on.timestamp())
    return resp


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
                "title": f"{user.username} Profile",
                "url": request.build_absolute_uri(reverse("user-profile")),
            }
        ]
        if user.is_superuser:
            links.append(
                {
                    "title": "Admin Area",
                    "url": request.build_absolute_uri(reverse("admin:index")),
                }
            )

        res = {"username": user.username, "links": links}

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


def registration_rate(self, group, request):
    registration_form = UserRegistrationForm(request.POST)
    if registration_form.is_valid():
        return None
    else:
        return "10/h"


@method_decorator(never_cache, name="dispatch")
class ConcordiaRegistrationView(RatelimitMixin, RegistrationView):
    form_class = UserRegistrationForm
    ratelimit_group = "registration"
    ratelimit_key = "ip"
    ratelimit_rate = registration_rate
    ratelimit_method = "POST"
    ratelimit_block = settings.RATELIMIT_BLOCK


@method_decorator(never_cache, name="dispatch")
class ConcordiaLoginView(RatelimitMixin, LoginView):
    ratelimit_group = "login"
    ratelimit_key = "post:username"
    ratelimit_rate = "3/15m"
    ratelimit_method = "POST"
    ratelimit_block = False
    form_class = UserLoginForm

    def post(self, request, *args, **kwargs):
        form = self.get_form()

        blocked = is_ratelimited(
            request,
            group=self.ratelimit_group,
            key=self.ratelimit_key,
            method=self.ratelimit_method,
            rate=self.ratelimit_rate,
        )
        recent_captcha = (
            time() - request.session.get("captcha_validation_time", 0)
        ) < 86400

        if blocked and not recent_captcha:
            form.fields["captcha"] = CaptchaField()

        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)


def ratelimit_view(request, exception=None):
    status_code = 429

    ctx = {
        "error": "You have been rate-limited. Please try again later.",
        "status": status_code,
    }

    if exception is not None:
        ctx["exception"]: str(exception)

    if request.is_ajax() or request_accepts_json(request):
        response = JsonResponse(ctx, status=status_code)
    else:
        response = render(request, "429.html", context=ctx, status=status_code)

    response["Retry-After"] = 15 * 60

    return response


@login_required
@never_cache
def AccountLetterView(request):
    # Generates a transcriptions and reviews contribution pdf letter for the user and downloads it
    date_today = datetime.datetime.now()
    username = request.user.email
    join_date = request.user.date_joined

    totalTranscriptions = 0
    totalReviews = 0
    user = request.user
    contributed_campaigns = (
        Campaign.objects.annotate(
            action_count=Count(
                "project__item__asset__transcription",
                filter=Q(project__item__asset__transcription__user=user)
                | Q(project__item__asset__transcription__reviewed_by=user),
            ),
            transcribe_count=Count(
                "project__item__asset__transcription",
                filter=Q(project__item__asset__transcription__user=user),
            ),
            review_count=Count(
                "project__item__asset__transcription",
                filter=Q(project__item__asset__transcription__reviewed_by=user),
            ),
        )
        .exclude(action_count=0)
        .order_by("title")
    )

    for campaign in contributed_campaigns:
        totalReviews = totalReviews + campaign.review_count
        totalTranscriptions = totalTranscriptions + campaign.transcribe_count
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margin(10)
    path = os.path.dirname(os.path.abspath(__file__)) + "/static/img/logo.jpg"
    pdf.add_page()
    pdf.image(
        path,
        x=12,
        y=15,
        w=60,
        type="",
        link="https://www.loc.gov/",
        alt_text="Library Logo",
    )
    pdf.set_author("By The People")
    pdf.set_creator("Concordia")
    pdf.set_subject("BTP Service Letter")
    pdf.set_keywords("SL Concordia BTP")
    pdf.set_title(title="Service Letter")
    pdf.set_lang("en-US")
    pdf.set_producer("Concordia")
    pdf.set_font("Arial", size=11)
    pdf.cell(60, 40, txt="", ln=1, align="L")
    pdf.cell(30, 5, txt="   Library of Congress", ln=1, align="L")
    pdf.cell(30, 5, txt="   101 Independence Avenue SE", ln=1, align="L")
    pdf.cell(30, 5, txt="   Washington, DC 20540", ln=1, align="L")
    pdf.cell(
        60,
        20,
        txt="   " + datetime.date.strftime(date_today, "%m/%d/%Y"),
        ln=1,
        align="L",
    )
    pdf.cell(60, 10, txt="  To whom it may concern,", ln=1, align="L")
    pdf.cell(
        140,
        5,
        txt="   I am writing to confirm this volunteer's participation in"
        " the Library of Congress"
        " virtual volunteering ",
        ln=1,
        align="L",
    )
    pdf.set_font("Arial", "I", 11)
    pdf.cell(
        60,
        5,
        txt="   program By the People ",
        align="L",
        link="https://crowd.loc.gov",
    )
    pdf.set_font("Arial", size=11)
    pdf.cell(
        90,
        5,
        txt=" (https://crowd.loc.gov). The project invites anyone to help the Library ",
        ln=1,
        align="C",
    )
    pdf.cell(
        120,
        5,
        txt="   by transcribing, tagging and reviewing transcriptions of digitized historical "
        "documents from ",
        ln=1,
        align="L",
    )
    pdf.cell(
        120,
        5,
        txt="   the Library's collections. These transcriptions make the content of handwritten and other documents ",
        ln=1,
        align="L",
    )
    pdf.cell(
        85,
        5,
        txt="   keyword searchable on the Library's main website (https://loc.gov), ",
        align="L",
        link="https://loc.gov",
    )
    pdf.cell(
        120,
        5,
        txt=" open new avenues of digital ",
        ln=1,
        align="C",
    )
    pdf.cell(
        120,
        5,
        txt="   research, and improve accessibility, including for people with visual or cognitive disabilities. ",
        ln=1,
        align="L",
    )
    pdf.cell(120, 5, txt="", ln=1, align="L")
    pdf.cell(40, 5, txt="   They registered as a ", ln=0, align="L")
    pdf.set_font("Arial", "I", 11)
    pdf.cell(24, 5, txt="By the People", ln=0, align="L", link="https://loc.gov")
    pdf.set_font("Arial", size=11)
    pdf.cell(
        0,
        5,
        txt=" volunteer on "
        + datetime.date.strftime(join_date, "%m/%d/%Y")
        + " as "
        + username
        + ". They made "
        + "{:,}".format(totalTranscriptions)
        + " edits ",
        ln=1,
        align="L",
    )
    pdf.cell(
        0,
        5,
        txt="   "
        + "to transcriptions"
        + " on the site and reviewed "
        + "{:,}".format(totalReviews)
        + " transcriptions by other volunteers. Their user profile  ",
        ln=1,
        align="L",
    )
    pdf.cell(0, 5, txt="   provides further details.", ln=1, align="L")
    pdf.cell(100, 12, txt="   Best,", ln=1, align="L")
    pdf.cell(110, 10, txt="   Lauren Algee", ln=1, align="L")
    pdf.cell(120, 5, txt="   crowd@loc.gov", ln=1, align="L")
    pdf.cell(14, 5, txt="   Community Manager, ", align="L")
    pdf.set_font("Arial", "I", 11)
    pdf.cell(80, 5, txt="By the People", ln=1, align="C")
    pdf.set_font("Arial", size=11)
    pdf.cell(140, 5, txt="   Digital Content Management Section", ln=1, align="L")
    pdf.cell(150, 5, txt="   Library of Congress ", ln=1, align="L")
    pdf.output("letter.pdf", "F")
    with open("letter.pdf", "rb") as f:
        response = HttpResponse(content=f.read(), content_type="application/pdf")
        response["Content-Disposition"] = "attachment; filename=letter.pdf"
        os.remove("letter.pdf")
        return response


@method_decorator(never_cache, name="dispatch")
class AccountProfileView(LoginRequiredMixin, FormView, ListView):
    template_name = "account/profile.html"
    form_class = UserProfileForm
    success_url = reverse_lazy("user-profile")

    # This view will list the assets which the user has contributed to
    # along with their most recent action on each asset. This will be
    # presented in the template as a standard paginated list of Asset
    # instances with annotations
    allow_empty = True
    paginate_by = 30

    def post(self, *args, **kwargs):
        self.object_list = self.get_queryset()
        self.object_list.sort(key=lambda x: x.last_interaction_time, reverse=True)
        return super().post(*args, **kwargs)

    def get_queryset(self):
        transcriptions = Transcription.objects.filter(
            Q(user=self.request.user) | Q(reviewed_by=self.request.user)
        )

        qId = self.request.GET.get("campaign_slug", None)

        if qId:
            campaignSlug = qId
            assets = Asset.objects.filter(
                transcription__in=transcriptions,
                item__project__campaign__pk=campaignSlug,
            ).order_by("-last_transcribed")
        else:
            campaignSlug = -1
            assets = Asset.objects.filter(transcription__in=transcriptions).order_by(
                "-last_transcribed"
            )

        assets = assets.select_related(
            "item", "item__project", "item__project__campaign"
        )
        assets = assets.annotate(
            last_transcribed=Max(
                "transcription__created_on",
                filter=Q(transcription__user=self.request.user),
            ),
            last_reviewed=Max(
                "transcription__updated_on",
                filter=Q(transcription__reviewed_by=self.request.user),
            ),
        )
        return assets

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data(*args, **kwargs)
        obj_list = ctx.pop("object_list")
        ctx["object_list"] = object_list = []

        qId = self.request.GET.get("campaign_slug", None)

        if qId:
            campaignSlug = qId
        else:
            campaignSlug = -1

        for asset in obj_list:

            if asset.last_reviewed:
                asset.last_interaction_time = asset.last_reviewed
                asset.last_interaction_type = "reviewed"
            else:
                asset.last_interaction_time = asset.last_transcribed
                asset.last_interaction_type = "transcribed"

            if int(campaignSlug) == -1:
                object_list.append((asset))
            else:
                if asset.item.project.campaign.id == int(campaignSlug):
                    object_list.append((asset))

        user = self.request.user
        object_list.sort(key=lambda x: x.last_interaction_time, reverse=True)

        contributed_campaigns = (
            Campaign.objects.annotate(
                action_count=Count(
                    "project__item__asset__transcription",
                    filter=Q(project__item__asset__transcription__user=user)
                    | Q(project__item__asset__transcription__reviewed_by=user),
                ),
                transcribe_count=Count(
                    "project__item__asset__transcription",
                    filter=Q(project__item__asset__transcription__user=user),
                ),
                review_count=Count(
                    "project__item__asset__transcription",
                    filter=Q(project__item__asset__transcription__reviewed_by=user),
                ),
            )
            .exclude(action_count=0)
            .order_by("title")
        )
        totalCount = 0
        totalTranscriptions = 0
        totalReviews = 0

        ctx["contributed_campaigns"] = contributed_campaigns

        for campaign in contributed_campaigns:
            campaign.action_count = campaign.transcribe_count + campaign.review_count
            totalCount = totalCount + campaign.review_count + campaign.transcribe_count
            totalReviews = totalReviews + campaign.review_count
            totalTranscriptions = totalTranscriptions + campaign.transcribe_count

        ctx["totalCount"] = totalCount
        ctx["totalReviews"] = totalReviews
        ctx["totalTranscriptions"] = totalTranscriptions
        return ctx

    def get_initial(self):
        initial = super().get_initial()
        initial["email"] = self.request.user.email
        return initial

    def get_form_kwargs(self):
        # We'll expose the request object to the form so we can validate that an
        # email is not in use by a *different* user:
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        user = self.request.user
        user.email = form.cleaned_data["email"]
        user.full_clean()
        user.save()

        return super().form_valid(form)


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

        ctx["slides"] = CarouselSlide.objects.published().order_by("ordering")

        if ctx["slides"]:
            ctx["firstslide"] = ctx["slides"][0]

        return ctx


@method_decorator(default_cache_control, name="dispatch")
class CampaignListView(APIListView):
    template_name = "transcriptions/campaign_list.html"
    paginate_by = 10

    queryset = Campaign.objects.published().listed().order_by("ordering", "title")
    context_object_name = "campaigns"

    def serialize_context(self, context):
        data = super().serialize_context(context)

        object_list = data["objects"]

        status_count_keys = {
            status: f"{status}_count" for status in TranscriptionStatus.CHOICE_MAP
        }

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
                    for k, v in status_count_keys.items()
                }
            )
            .values("pk", *status_count_keys.values())
        )

        campaign_asset_counts = {}
        for campaign_stats in campaign_stats_qs:
            campaign_asset_counts[campaign_stats.pop("pk")] = campaign_stats

        for obj in object_list:
            obj["asset_stats"] = campaign_asset_counts[obj["id"]]

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

        for k, _ in TranscriptionStatus.CHOICES:
            counts[k] = getattr(obj, f"{k}_count", 0)

        obj.total_count = total = sum(counts.values())

        lowest_status = None

        for k, _ in TranscriptionStatus.CHOICES:
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

        status_count_keys = {
            status: f"{status}_count" for status in TranscriptionStatus.CHOICE_MAP
        }

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
                    for k, v in status_count_keys.items()
                }
            )
            .values("pk", *status_count_keys.values())
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
            Campaign.objects.published().listed().order_by("ordering", "title")
        )
        data["topics"] = (
            Topic.objects.published().listed().order_by("ordering", "title")
        )
        data["campaigns_topics"] = sorted(
            [*data["campaigns"], *data["topics"]], key=attrgetter("ordering", "title")
        )

        return render(self.request, self.template_name, data)


@method_decorator(default_cache_control, name="dispatch")
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
            for title, url in self.object.resource_set.values_list(
                "title", "resource_url"
            )
        ]
        return ctx


@method_decorator(default_cache_control, name="dispatch")
class CampaignDetailView(APIDetailView):
    template_name = "transcriptions/campaign_detail.html"
    context_object_name = "campaign"
    queryset = Campaign.objects.published().order_by("title")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        projects = (
            ctx["campaign"]
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
                    for key in TranscriptionStatus.CHOICE_MAP
                }
            )
            .order_by("ordering", "title")
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

        campaign_assets = Asset.objects.filter(
            item__project__campaign=self.object,
            item__project__published=True,
            item__published=True,
            published=True,
        )

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


@method_decorator(default_cache_control, name="dispatch")
class ProjectDetailView(APIListView):
    template_name = "transcriptions/project_detail.html"
    context_object_name = "items"
    paginate_by = 10

    def get_queryset(self):
        self.project = get_object_or_404(
            Project.objects.published().select_related("campaign"),
            slug=self.kwargs["slug"],
            campaign__slug=self.kwargs["campaign_slug"],
        )

        item_qs = self.project.item_set.published().order_by("item_id")
        item_qs = item_qs.annotate(
            **{
                f"{key}_count": Count(
                    "asset", filter=Q(asset__transcription_status=key)
                )
                for key in TranscriptionStatus.CHOICE_MAP
            }
        )

        self.filters = {}
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

        calculate_asset_stats(project_assets, ctx)

        annotate_children_with_progress_stats(ctx["items"])

        return ctx

    def serialize_context(self, context):
        data = super().serialize_context(context)
        data["project"] = self.serialize_object(context["project"])
        return data


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

    def get_queryset(self):
        self.item = get_object_or_404(
            Item.objects.published().select_related("project__campaign"),
            project__campaign__slug=self.kwargs["campaign_slug"],
            project__slug=self.kwargs["project_slug"],
            item_id=self.kwargs["item_id"],
        )

        asset_qs = self.item.asset_set.published().order_by("sequence")
        asset_qs = asset_qs.select_related(
            "item__project__campaign", "item__project", "item"
        )

        self.filters = {}
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

        item_assets = self.item.asset_set.published()

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


@method_decorator(never_cache, name="dispatch")
class AssetDetailView(APIDetailView):
    """
    Class to handle GET ansd POST requests on route /campaigns/<campaign>/asset/<asset>
    """

    template_name = "transcriptions/asset_detail.html"

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

        return ctx


@never_cache
def ajax_captcha(request):
    if request.method == "POST":
        response = request.POST.get("response")
        key = request.POST.get("key")

        if response and key:
            CaptchaStore.remove_expired()

            # Note that CaptchaStore displays the response in uppercase in the
            # image and in the string representation of the object but the
            # actual value stored in the database is lowercase!
            deleted, _ = CaptchaStore.objects.filter(
                response=response.lower(), hashkey=key
            ).delete()

            if deleted > 0:
                request.session["captcha_validation_time"] = time()
                return JsonResponse({"valid": True})

    key = CaptchaStore.generate_key()
    return JsonResponse(
        {"key": key, "image": request.build_absolute_uri(captcha_image_url(key))},
        status=401,
        content_type="application/json",
    )


def validate_anonymous_captcha(view):
    @wraps(view)
    @never_cache
    def inner(request, *args, **kwargs):
        if not request.user.is_authenticated:
            captcha_last_validated = request.session.get("captcha_validation_time", 0)
            age = time() - captcha_last_validated
            if age > settings.ANONYMOUS_CAPTCHA_VALIDATION_INTERVAL:
                return ajax_captcha(request)

        return view(request, *args, **kwargs)

    return inner


@require_POST
@validate_anonymous_captcha
@atomic
def save_transcription(request, *, asset_pk):
    asset = get_object_or_404(Asset, pk=asset_pk)

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
    if not supersedes_pk:
        superseded = None
        if asset.transcription_set.filter(supersedes=None).exists():
            return JsonResponse(
                {"error": "An open transcription already exists"}, status=409
            )
    else:
        if asset.transcription_set.filter(supersedes=supersedes_pk).exists():
            return JsonResponse(
                {"error": "This transcription has been superseded"}, status=409
            )

        try:
            superseded = asset.transcription_set.get(pk=supersedes_pk)
        except Transcription.DoesNotExist:
            return JsonResponse({"error": "Invalid supersedes value"}, status=400)

    transcription = Transcription(
        asset=asset, user=user, supersedes=superseded, text=transcription_text
    )
    transcription.full_clean()
    transcription.save()

    return JsonResponse(
        {
            "id": transcription.pk,
            "sent": time(),
            "submissionUrl": reverse("submit-transcription", args=(transcription.pk,)),
            "asset": {
                "id": transcription.asset.id,
                "status": transcription.asset.transcription_status,
            },
        },
        status=201,
    )


@require_POST
@validate_anonymous_captcha
def submit_transcription(request, *, pk):
    transcription = get_object_or_404(Transcription, pk=pk)

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

    return JsonResponse(
        {
            "id": transcription.pk,
            "sent": time(),
            "asset": {
                "id": transcription.asset.id,
                "status": transcription.asset.transcription_status,
            },
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

    return JsonResponse(
        {
            "id": transcription.pk,
            "sent": time(),
            "asset": {
                "id": transcription.asset.id,
                "status": transcription.asset.transcription_status,
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

    for tag in existing_user_tags:
        if tag not in all_submitted_tags:
            user_tags.tags.remove(tag)

    all_tags_qs = Tag.objects.filter(userassettagcollection__asset__pk=asset_pk)
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

        initial["referrer"] = self.request.META.get("HTTP_REFERER")

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
                "Unable to send contact message to %s: %s",
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
            return redirect(self.request.path)

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
        projects_page = paginator.get_page(page)
        if page > paginator.num_pages:
            return redirect(self.request.path)

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


def reserve_rate(g, r):
    return None if r.user.is_authenticated else "100/m"


@ratelimit(key="ip", rate=reserve_rate, block=settings.RATELIMIT_BLOCK)
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
                    logger.debug(
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


@never_cache
@atomic
def redirect_to_next_reviewable_asset(request):
    campaign = Campaign.objects.published().listed().order_by("ordering")[0]
    project_slug = request.GET.get("project", "")
    item_id = request.GET.get("item", "")
    asset_id = request.GET.get("asset", 0)

    # FIXME: ensure the project belongs to the campaign

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


def find_transcribable_assets(campaign_counter, project_slug, item_id, asset_id):
    campaigns = Campaign.objects.published().listed().order_by("ordering")
    potential_assets = Asset.objects.select_for_update(skip_locked=True, of=("self",))
    potential_assets = potential_assets.filter(
        item__project__campaign=campaigns[campaign_counter],
        item__project__published=True,
        item__published=True,
        published=True,
    )
    # FIXME: if project is specified, the campaign can only be
    # that project's campaign
    potential_assets = filter_and_order_transcribable_assets(
        potential_assets, project_slug, item_id, asset_id
    )

    return potential_assets


@never_cache
@atomic
def redirect_to_next_transcribable_asset(request):
    # Campaign is not specified, but project / item / asset may be
    if not request.user.is_authenticated:
        user = get_anonymous_user()
    else:
        user = request.user

    project_slug = request.GET.get("project", "")
    item_id = request.GET.get("item", "")
    asset_id = request.GET.get("asset", 0)

    # FIXME: if the project is specified, select the campaign
    # to which it belongs

    potential_assets = None
    campaign_counter = 0

    while not potential_assets:
        potential_assets = find_transcribable_assets(
            campaign_counter, project_slug, item_id, asset_id
        )
        campaign_counter = campaign_counter + 1

    return redirect_to_next_asset(
        potential_assets, "transcribe", request, project_slug, user
    )


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


class AssetListView(APIListView):
    context_object_name = "assets"
    paginate_by = 50
    queryset = Asset.objects.published()

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset()

        pks = self.request.GET.getlist("pk")

        if pks:
            try:
                qs = qs.filter(pk__in=pks)
            except (ValueError, TypeError):
                raise Http404

        latest_transcription_qs = (
            Transcription.objects.filter(asset=OuterRef("pk"))
            .order_by("-pk")
            .values_list("pk", flat=True)
        )

        qs = qs.annotate(latest_transcription_pk=Subquery(latest_transcription_qs[:1]))

        return qs.prefetch_related("item", "item__project", "item__project__campaign")

    def get_ordering(self):
        order_field = self.request.GET.get("order_by", "pk")
        if order_field.lstrip("-") not in ("pk", "difficulty"):
            raise ValueError
        return order_field

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        assets = ctx["assets"]
        asset_pks = [i.pk for i in assets]

        latest_transcriptions = {
            asset_id: {"id": id, "submitted_by": user_id, "text": text}
            for id, asset_id, user_id, text in Transcription.objects.filter(
                pk__in=[i.latest_transcription_pk for i in assets]
            ).values_list("id", "asset_id", "user_id", "text")
        }

        adjacent_asset_qs = Asset.objects.filter(
            published=True, item=OuterRef("item")
        ).values("sequence")

        adjacent_seq_qs = (
            Asset.objects.filter(pk__in=asset_pks, published=True)
            .annotate(
                next_sequence=Subquery(
                    adjacent_asset_qs.filter(
                        sequence__gt=OuterRef("sequence")
                    ).order_by("sequence")[:1]
                ),
                previous_sequence=Subquery(
                    adjacent_asset_qs.filter(
                        sequence__lt=OuterRef("sequence")
                    ).order_by("-sequence")[:1]
                ),
            )
            .values_list("pk", "previous_sequence", "next_sequence")
        )

        adjacent_seqs = {
            pk: (prev_seq, next_seq) for pk, prev_seq, next_seq in adjacent_seq_qs
        }

        for asset in assets:
            asset.latest_transcription = latest_transcriptions.get(asset.pk, None)

            asset.previous_sequence, asset.next_sequence = adjacent_seqs.get(
                asset.id, (None, None)
            )

        return ctx

    def serialize_object(self, obj):
        # Since we're doing this a lot, let's avoid some repetitive lookups:
        item = obj.item
        project = item.project
        campaign = project.campaign

        image_url, thumbnail_url = get_image_urls_from_asset(obj)

        metadata = {
            "id": obj.pk,
            "status": obj.transcription_status,
            "url": obj.get_absolute_url(),
            "thumbnailUrl": thumbnail_url,
            "imageUrl": image_url,
            "title": obj.title,
            "difficulty": obj.difficulty,
            "year": obj.year,
            "sequence": obj.sequence,
            "resource_url": obj.resource_url,
            "latest_transcription": obj.latest_transcription,
            "item": {
                "id": item.pk,
                "item_id": item.item_id,
                "title": item.title,
                "url": item.get_absolute_url(),
            },
            "project": {
                "id": project.pk,
                "slug": project.slug,
                "title": project.title,
                "url": project.get_absolute_url(),
            },
            "campaign": {
                "id": campaign.pk,
                "title": campaign.title,
                "url": campaign.get_absolute_url(),
            },
        }

        if project.topics:
            metadata["topics"] = []

            for topic in project.topics.all():
                new_topic = {}
                new_topic["id"] = topic.pk
                new_topic["title"] = topic.title
                new_topic["url"] = topic.get_absolute_url()
                metadata["topics"].append(new_topic)

        # FIXME: we want to rework how this is done after deprecating Asset.media_url
        if obj.previous_sequence:
            metadata["previous_thumbnail"] = re.sub(
                r"[/]\d+[.]jpg", f"/{obj.previous_sequence}.jpg", image_url
            )
        if obj.next_sequence:
            metadata["next_thumbnail"] = re.sub(
                r"[/]\d+[.]jpg", f"/{obj.next_sequence}.jpg", image_url
            )

        return metadata


class TranscribeListView(AssetListView):
    template_name = "transcriptions/transcribe_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["campaigns"] = Campaign.objects.published().listed().order_by("title")
        return ctx

    def get_queryset(self):
        asset_qs = super().get_queryset()

        asset_qs = asset_qs.filter(
            Q(transcription_status=TranscriptionStatus.NOT_STARTED)
            | Q(transcription_status=TranscriptionStatus.IN_PROGRESS)
        )

        campaign_filter = self.request.GET.get("campaign_filter")
        if campaign_filter:
            asset_qs = asset_qs.filter(item__project__campaign__pk=campaign_filter)

        order_field = self.get_ordering()
        if order_field:
            asset_qs.order_by(order_field)

        return asset_qs


class ReviewListView(AssetListView):
    template_name = "transcriptions/review_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["campaigns"] = Campaign.objects.published().listed().order_by("title")
        return ctx

    def get_queryset(self):
        asset_qs = super().get_queryset()

        asset_qs = asset_qs.filter(transcription_status=TranscriptionStatus.SUBMITTED)

        campaign_filter = self.request.GET.get("campaign_filter")

        if campaign_filter:
            asset_qs = asset_qs.filter(item__project__campaign__pk=campaign_filter)

        order_field = self.get_ordering()
        if order_field:
            asset_qs.order_by(order_field)

        return asset_qs


@flag_required("ACTIVITY_UI_ENABLED")
@login_required
@never_cache
def action_app(request):
    return render(
        request,
        "action-app.html",
        {
            "app_parameters": {
                "currentUser": request.user.pk,
                "reservationToken": get_or_create_reservation_token(request),
                "urls": {
                    "assetUpdateSocket": request.build_absolute_uri(
                        "/ws/asset/asset_updates/"
                    ).replace("http", "ws"),
                    "campaignList": reverse("transcriptions:campaign-list"),
                    "topicList": reverse("topic-list"),
                },
                "urlTemplates": {
                    "assetData": "/{action}/?per_page=500",
                    "assetReservation": "/reserve-asset/{assetId}/",
                    "saveTranscription": "/assets/{assetId}/transcriptions/save/",
                    "submitTranscription": "/transcriptions/{transcriptionId}/submit/",
                    "reviewTranscription": "/transcriptions/{transcriptionId}/review/",
                },
            }
        },
    )
