import json
import os
import re
import time
from datetime import timedelta
from functools import wraps
from logging import getLogger
from smtplib import SMTPException

import markdown
from captcha.helpers import captcha_image_url
from captcha.models import CaptchaStore
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Count, Q
from django.db.transaction import atomic
from django.http import HttpResponse, JsonResponse
from django.shortcuts import Http404, get_object_or_404, redirect, render
from django.template import loader
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.timezone import now
from django.views.decorators.cache import cache_control, never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.decorators.vary import vary_on_headers
from django.views.generic import DetailView, FormView, ListView, TemplateView
from django_registration.backends.activation.views import RegistrationView
from ratelimit.decorators import ratelimit
from ratelimit.mixins import RatelimitMixin

from concordia.forms import (
    AssetFilteringForm,
    ContactUsForm,
    UserProfileForm,
    UserRegistrationForm,
)
from concordia.models import (
    Asset,
    AssetTranscriptionReservation,
    Campaign,
    Item,
    Project,
    Tag,
    Transcription,
    TranscriptionStatus,
    UserAssetTagCollection,
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


def get_anonymous_user():
    """
    Get the user called "anonymous" if it exist. Create the user if it doesn't
    exist This is the default concordia user if someone is working on the site
    without logging in first.
    """

    try:
        return User.objects.get(username="anonymous")
    except User.DoesNotExist:
        return User.objects.create_user(username="anonymous")


@never_cache
def healthz(request):
    status = {"current_time": time.time(), "load_average": os.getloadavg()}

    # We don't want to query a large table but we do want to hit the database
    # at last once:
    status["database_has_data"] = Campaign.objects.count() > 0

    status["application_version"] = get_concordia_version()

    return HttpResponse(content=json.dumps(status), content_type="application/json")


@default_cache_control
def static_page(request, base_name=None):
    """
    Serve static content from Markdown files

    Expects the request path with the addition of ".md" to match a file under
    the top-level static-pages directory or the url dispatcher configuration to
    pass a base_name parameter:

    path("foobar/", static_page, {"base_name": "some-weird-filename.md"})
    """

    if not base_name:
        base_name = request.path.strip("/")

    filename = os.path.join(settings.SITE_ROOT_DIR, "static-pages", f"{base_name}.md")

    if not os.path.exists(filename):
        raise Http404

    md = markdown.Markdown(extensions=["meta"])
    with open(filename) as f:
        html = md.convert(f.read())

    page_title = md.Meta.get("title")
    if page_title:
        page_title = "\n".join(i.strip() for i in page_title)
    else:
        page_title = base_name.replace("-", " ").replace("/", " — ").title()

    breadcrumbs = []
    path_components = request.path.strip("/").split("/")
    for i, segment in enumerate(path_components, start=1):
        breadcrumbs.append(
            ("/%s/" % "/".join(path_components[0:i]), segment.replace("-", " ").title())
        )

    ctx = {"body": html, "title": page_title, "breadcrumbs": breadcrumbs}

    return render(request, "static-page.html", ctx)


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


def registration_rate(self, group, request):
    registration_form = UserRegistrationForm(request.POST)
    if registration_form.is_valid():
        return None
    else:
        return "10/h"


@method_decorator(never_cache, name="dispatch")
class ConcordiaRegistrationView(RatelimitMixin, RegistrationView):
    form_class = UserRegistrationForm
    ratelimit_key = "ip"
    ratelimit_rate = registration_rate
    ratelimit_method = "POST"
    ratelimit_block = True


@method_decorator(never_cache, name="dispatch")
class ConcordiaLoginView(RatelimitMixin, LoginView):
    ratelimit_key = "ip"
    ratelimit_rate = "3/15m"
    ratelimit_method = "POST"
    ratelimit_block = True


def ratelimit_view(request, exception=None):
    template_name = "429.html"
    status_code = 429
    template = loader.get_template(template_name)
    return HttpResponse(template.render(), status=status_code)


@method_decorator(never_cache, name="dispatch")
class AccountProfileView(LoginRequiredMixin, FormView):
    template_name = "account/profile.html"
    form_class = UserProfileForm
    success_url = reverse_lazy("user-profile")

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data(*args, **kwargs)
        ctx["transcriptions"] = (
            Transcription.objects.filter(user=self.request.user)
            .select_related("asset__item__project__campaign")
            .order_by("asset__pk", "-pk")
            .distinct("asset")
        )
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

    queryset = Campaign.objects.published().order_by("title")
    context_object_name = "campaigns"


@method_decorator(default_cache_control, name="dispatch")
class CampaignListView(ListView):
    template_name = "transcriptions/campaign_list.html"
    paginate_by = 10

    queryset = Campaign.objects.published().order_by("title")
    context_object_name = "campaigns"


def calculate_asset_stats(asset_qs, ctx):
    asset_count = asset_qs.count()

    trans_qs = Transcription.objects.filter(asset__in=asset_qs)
    ctx["contributor_count"] = (
        User.objects.filter(
            Q(transcription__in=trans_qs) | Q(transcription_reviewers__in=trans_qs)
        )
        .distinct()
        .count()
    )

    asset_state_qs = asset_qs.values_list("transcription_status")
    asset_state_qs = asset_state_qs.annotate(Count("transcription_status")).order_by()
    state_counts = dict(asset_state_qs)

    if "edit" in state_counts:
        # Correct semantic difference between our normal “open for edit”
        # including assets with no progress at all:
        state_counts["edit"] -= asset_qs.filter(transcription=None).count()

    for state in TranscriptionStatus.CHOICE_MAP.keys():
        value = state_counts.get(state, 0)
        if value:
            pct = round(100 * (value / asset_count))
        else:
            pct = 0

        ctx[f"{state}_percent"] = pct


@method_decorator(default_cache_control, name="dispatch")
class CampaignDetailView(DetailView):
    template_name = "transcriptions/campaign_detail.html"

    queryset = Campaign.objects.published().order_by("title")
    context_object_name = "campaign"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        campaign_assets = Asset.objects.filter(
            item__project__campaign=self.object,
            item__project__published=True,
            item__published=True,
            published=True,
        )

        calculate_asset_stats(campaign_assets, ctx)

        return ctx


@method_decorator(default_cache_control, name="dispatch")
class ProjectDetailView(ListView):
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

        return item_qs

    def get_context_data(self, **kws):
        ctx = super().get_context_data(**kws)
        ctx["project"] = project = self.project
        ctx["campaign"] = project.campaign

        project_assets = Asset.objects.filter(
            item__project=project, published=True, item__published=True
        )

        calculate_asset_stats(project_assets, ctx)

        return ctx


@method_decorator(default_cache_control, name="dispatch")
class ItemDetailView(ListView):
    """
    Handle GET requests on /campaign/<campaign>/<project>/<item>

    This uses a ListView to paginate the item's assets
    """

    template_name = "transcriptions/item_detail.html"
    context_object_name = "assets"
    paginate_by = 10

    form_class = AssetFilteringForm

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
        return self.apply_asset_filters(asset_qs)

    def apply_asset_filters(self, asset_qs):
        """Use optional GET parameters to filter the asset list"""

        # We want to get a list of all of the available asset states in this
        # item's assets and will return that with the preferred display labels
        # including the asset count to be displayed in the filter UI
        asset_state_qs = asset_qs.values_list("transcription_status")
        asset_state_qs = asset_state_qs.annotate(
            Count("transcription_status")
        ).order_by()

        self.transcription_status_counts = status_counts = dict(asset_state_qs)

        self.filter_form = form = self.form_class(status_counts, self.request.GET)
        if form.is_valid():
            asset_qs = asset_qs.filter(
                **{k: v for k, v in form.cleaned_data.items() if v}
            )

        return asset_qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        ctx.update(
            {
                "campaign": self.item.project.campaign,
                "project": self.item.project,
                "item": self.item,
                "filter_form": self.filter_form,
                "transcription_status_counts": self.transcription_status_counts,
            }
        )

        item_assets = self.item.asset_set.published()

        calculate_asset_stats(item_assets, ctx)

        return ctx


@method_decorator(never_cache, name="dispatch")
class AssetDetailView(DetailView):
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

        # We'll handle the case where an item with no transcriptions should be
        # shown as status=edit here so the logic doesn't need to be repeated in
        # templates:
        if transcription:
            transcription_status = transcription.status.lower()
        else:
            transcription_status = "edit"
        ctx["transcription_status"] = transcription_status

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

        tag_groups = UserAssetTagCollection.objects.filter(asset__slug=asset.slug)
        ctx["tags"] = tags = []

        for tag_group in tag_groups:
            for tag in tag_group.tags.all():
                tags.append(tag)

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
                request.session["captcha_validation_time"] = time.time()
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
            age = time.time() - captcha_last_validated
            if age > settings.ANONYMOUS_CAPTCHA_VALIDATION_INTERVAL:
                return ajax_captcha(request)

        return view(request, *args, **kwargs)

    return inner


def save_rate(g, r):
    return None if r.user.is_authenticated else "1/m"


@ratelimit(key="ip", rate=save_rate, block=True)
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
            "submissionUrl": reverse("submit-transcription", args=(transcription.pk,)),
        },
        status=201,
    )


def submit_rate(g, r):
    return None if r.user.is_authenticated else "1/m"


@ratelimit(key="ip", rate=submit_rate, block=True)
@require_POST
@validate_anonymous_captcha
def submit_transcription(request, *, pk):
    transcription = get_object_or_404(Transcription, pk=pk)

    if (
        transcription.submitted
        or transcription.asset.transcription_set.filter(supersedes=pk).exists()
    ):
        return JsonResponse(
            {
                "error": "This transcription has already been updated."
                " Reload the current status before continuing."
            },
            status=400,
        )

    transcription.submitted = now()
    transcription.full_clean()
    transcription.save()

    return JsonResponse({"id": transcription.pk}, status=200)


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

    if transcription.user.pk == request.user.pk:
        logger.warning("Attempted self-review for transcription %s", transcription)
        return JsonResponse(
            {"error": "You cannot review your own transcription"}, status=400
        )

    transcription.reviewed_by = request.user

    if action == "accept":
        transcription.accepted = now()
    else:
        transcription.rejected = now()

    transcription.full_clean()
    transcription.save()

    return JsonResponse({"id": transcription.pk}, status=200)


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

        try:
            send_mail(
                "Contact {}: {}".format(
                    self.request.get_host(), form.cleaned_data["subject"]
                ),
                message=text_message,
                html_message=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.DEFAULT_TO_EMAIL],
            )

            messages.success(self.request, "Your contact message has been sent.")
        except SMTPException as exc:
            logger.error(
                "Unable to send contact message to %s: %s",
                settings.DEFAULT_TO_EMAIL,
                exc,
                exc_info=True,
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
        except SMTPException as exc:
            logger.error(
                "Unable to send contact message to %s: %s",
                form.cleaned_data["email"],
                exc,
                exc_info=True,
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
            project.transcription_statuses


def reserve_rate(g, r):
    return None if r.user.is_authenticated else "12/m"


@ratelimit(key="ip", rate=reserve_rate, block=True)
@require_POST
@never_cache
def reserve_asset_transcription(request, *, asset_pk):
    """
    Receives an asset PK and attempts to create/update a reservation for it

    Returns HTTP 204 on success and HTTP 409 when the record is in use
    """

    if not request.user.is_authenticated:
        user = get_anonymous_user()
    else:
        user = request.user

    timestamp = now()

    # First clear old reservations, with a grace period:
    cutoff = timestamp - (
        timedelta(seconds=2 * settings.TRANSCRIPTION_RESERVATION_SECONDS)
    )

    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM concordia_assettranscriptionreservation WHERE updated_on < %s",
            [cutoff],
        )

    if request.POST.get("release"):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM concordia_assettranscriptionreservation
                WHERE user_id = %s AND asset_id = %s
                """,
                [user.pk, asset_pk],
            )
        return HttpResponse(status=204)

    # We're relying on the database to meet our integrity requirements and since
    # this is called periodically we want to be fairly fast until we switch to
    # something like Redis.

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO concordia_assettranscriptionreservation AS atr
                (user_id, asset_id, created_on, updated_on)
                VALUES (%s, %s, current_timestamp, current_timestamp)
            ON CONFLICT (asset_id) DO UPDATE
                SET updated_on = current_timestamp
                WHERE (
                    atr.user_id = excluded.user_id
                    AND atr.asset_id = excluded.asset_id
                )
            """.strip(),
            [user.pk, asset_pk],
        )

        if cursor.rowcount != 1:
            return HttpResponse(status=409)

    return HttpResponse(status=204)


@never_cache
@atomic
def redirect_to_next_transcribable_asset(request, *, campaign_slug, project_slug):
    project = get_object_or_404(
        Project.objects.published(), campaign__slug=campaign_slug, slug=project_slug
    )

    if not request.user.is_authenticated:
        user = get_anonymous_user()
    else:
        user = request.user

    potential_assets = Asset.objects.select_for_update(skip_locked=True, of=("self",))
    potential_assets = potential_assets.filter(
        item__project=project, transcription_status=TranscriptionStatus.EDIT
    )
    potential_assets = potential_assets.filter(assettranscriptionreservation=None)

    for potential_asset in potential_assets:
        res = AssetTranscriptionReservation(user=user, asset=potential_asset)
        res.full_clean()
        res.save()
        return redirect(
            "transcriptions:asset-detail",
            project.campaign.slug,
            project.slug,
            potential_asset.item.item_id,
            potential_asset.slug,
        )
    else:
        messages.info(
            request, "There are no remaining pages to be transcribed in this project!"
        )
        return redirect(
            "transcriptions:project-detail", project.campaign.slug, project.slug
        )
