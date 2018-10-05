import json
import os
import time
from datetime import datetime, timedelta
from logging import getLogger
from smtplib import SMTPException

import markdown
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Count
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import Http404, get_object_or_404, redirect, render
from django.template import loader
from django.urls import reverse_lazy
from django.utils.timezone import now
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, FormView, ListView, TemplateView, View
from django_registration.backends.activation.views import RegistrationView

from concordia.forms import (
    AssetFilteringForm,
    CaptchaEmbedForm,
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
    Status,
    Transcription,
    UserAssetTagCollection,
)
from concordia.version import get_concordia_version

logger = getLogger(__name__)

ASSETS_PER_PAGE = 36
PROJECTS_PER_PAGE = 36
ITEMS_PER_PAGE = 36


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

    ctx = {"body": html, "title": page_title}

    return render(request, "static-page.html", ctx)


class ConcordiaRegistrationView(RegistrationView):
    form_class = UserRegistrationForm


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


class HomeView(ListView):
    template_name = "home.html"

    queryset = Campaign.objects.published().order_by("title")
    context_object_name = "campaigns"


class CampaignListView(ListView):
    template_name = "transcriptions/campaign_list.html"
    paginate_by = 10

    queryset = Campaign.objects.published().order_by("title")
    context_object_name = "campaigns"


class CampaignDetailView(DetailView):
    template_name = "transcriptions/campaign_detail.html"

    queryset = Campaign.objects.published().order_by("title")
    context_object_name = "campaign"

    def get_queryset(self):
        return Campaign.objects.filter(slug=self.kwargs["slug"])


class ConcordiaProjectView(ListView):
    template_name = "transcriptions/project.html"
    context_object_name = "items"
    paginate_by = 10

    def get_queryset(self):
        self.project = Project.objects.select_related("campaign").get(
            slug=self.kwargs["slug"], campaign__slug=self.kwargs["campaign_slug"]
        )

        item_qs = self.project.item_set.order_by("item_id")

        if not self.request.user.is_staff:
            item_qs = item_qs.exclude(published=False)

        return item_qs

    def get_context_data(self, **kws):
        return dict(
            super().get_context_data(**kws),
            campaign=self.project.campaign,
            project=self.project,
        )


class ConcordiaItemView(ListView):
    # FIXME: review naming – we treat these as list views for sub-components and
    # might want to change / combine some views
    """
    Handle GET requests on /campaign/<campaign>/<project>/<item>
    """

    template_name = "transcriptions/item.html"
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

        asset_qs = self.item.asset_set.all().order_by("sequence")
        asset_qs = asset_qs.select_related(
            "item__project__campaign", "item__project", "item"
        )
        return self.apply_asset_filters(asset_qs)

    def apply_asset_filters(self, asset_qs):
        """Use optional GET parameters to filter the asset list"""

        self.filter_form = form = self.form_class(asset_qs, self.request.GET)
        if form.is_valid():
            asset_qs = asset_qs.filter(
                **{k: v for k, v in form.cleaned_data.items() if v}
            )

        return asset_qs

    def get_context_data(self, **kwargs):
        res = super().get_context_data(**kwargs)

        res.update(
            {
                "campaign": self.item.project.campaign,
                "project": self.item.project,
                "item": self.item,
                "filter_form": self.filter_form,
            }
        )
        return res


class ConcordiaAssetView(DetailView):
    """
    Class to handle GET ansd POST requests on route /campaigns/<campaign>/asset/<asset>
    """

    template_name = "transcriptions/asset_detail.html"

    state_dictionary = {
        "Save": Status.EDIT,
        "Submit for Review": Status.SUBMITTED,
        "Mark Completed": Status.COMPLETED,
    }

    def get_queryset(self):
        asset_qs = Asset.objects.filter(
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

        previous_asset = (
            item.asset_set.filter(sequence__lt=asset.sequence)
            .order_by("sequence")
            .last()
        )
        next_asset = (
            item.asset_set.filter(sequence__gt=asset.sequence)
            .order_by("sequence")
            .first()
        )
        if previous_asset:
            ctx["previous_asset_url"] = previous_asset.get_absolute_url()
        if next_asset:
            ctx["next_asset_url"] = next_asset.get_absolute_url()

        # Get the most recent transcription
        latest_transcriptions = Transcription.objects.filter(
            asset__slug=asset.slug
        ).order_by("-updated_on")

        if latest_transcriptions:
            transcription = latest_transcriptions[0]
        else:
            transcription = None

        tag_groups = UserAssetTagCollection.objects.filter(asset__slug=asset.slug)
        tags = []

        for tag_group in tag_groups:
            for tag in tag_group.tags.all():
                tags.append(tag)

        captcha_form = CaptchaEmbedForm()

        if self.request.user.is_anonymous:
            ctx[
                "is_anonymous_user_captcha_validated"
            ] = self.is_anonymous_user_captcha_validated()

        ctx.update(
            {
                "page_in_use": False,
                "transcription": transcription,
                "transcription_status": transcription.status
                if transcription
                else Status.EDIT,
                "tags": tags,
                "captcha_form": captcha_form,
            }
        )

        return ctx

    def is_anonymous_user_captcha_validated(self):
        if "captcha_validated_at" in self.request.session:
            if (
                datetime.now().timestamp()
                - self.request.session["captcha_validated_at"]
            ) <= getattr(settings, "CAPTCHA_SESSION_VALID_TIME", 24 * 60 * 60):
                return True
        return False


class ConcordiaAlternateAssetView(View):
    """
    Class to handle when user opts to work on an alternate asset because another user is already working
    on the original page
    """

    def post(self, *args, **kwargs):
        """
        handle the POST request from the AJAX call in the template when user opts to work on alternate page
        :param request:
        :param args:
        :param kwargs:
        :return: alternate url the client will use to redirect to
        """

        if self.request.is_ajax():
            json_dict = json.loads(self.request.body)
            campaign_slug = json_dict["campaign"]
            asset_slug = json_dict["asset"]
        else:
            campaign_slug = self.request.POST.get("campaign", None)
            asset_slug = self.request.POST.get("asset", None)

        if campaign_slug and asset_slug:
            response = requests.get(
                "%s://%s/ws/campaign_asset_random/%s/%s"
                % (
                    self.request.scheme,
                    self.request.get_host(),
                    campaign_slug,
                    asset_slug,
                ),
                cookies=self.request.COOKIES,
            )
            random_asset_json_val = json.loads(response.content.decode("utf-8"))

            return HttpResponse(
                "/campaigns/%s/asset/%s/"
                % (campaign_slug, random_asset_json_val["slug"])
            )


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

        try:
            send_mail(
                "Contact Us: %(subject)s" % form.cleaned_data,
                message=text_message,
                html_message=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.DEFAULT_TO_EMAIL],
            )

            messages.success(self.request, "Your contact message has been sent...")
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

        return redirect("contact")


class ExperimentsView(TemplateView):
    def get_template_names(self):
        return ["experiments/{}.html".format(self.args[0])]


class CampaignView(TemplateView):
    template_name = "transcriptions/create.html"

    def get(self, *args, **kwargs):
        """
        GET request to create a collection. Only allow admin access
        :param args:
        :param kwargs:
        :return: redirect to home (/) or render template create.html
        """
        if not self.request.user.is_superuser:
            return HttpResponseRedirect("/")
        else:
            return render(self.request, self.template_name)


class ReportCampaignView(TemplateView):
    """
    Report about campaign resources and status
    """

    template_name = "transcriptions/report.html"

    def get(self, request, campaign_slug):
        campaign = get_object_or_404(Campaign, slug=campaign_slug)

        try:
            page = int(self.request.GET.get("page", "1"))
        except ValueError:
            return redirect(self.request.path)

        ctx = {
            "title": campaign.title,
            "campaign_slug": campaign.slug,
            "total_asset_count": campaign.asset_set.count(),
        }

        projects_qs = campaign.project_set.order_by("title")

        projects_qs = projects_qs.annotate(asset_count=Count("asset"))
        projects_qs = projects_qs.annotate(
            tag_count=Count("asset__userassettagcollection__tags", distinct=True)
        )
        projects_qs = projects_qs.annotate(
            contributor_count=Count(
                "asset__userassettagcollection__user", distinct=True
            )
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
        status_qs = Transcription.objects.filter(asset__project__in=projects)
        status_qs = status_qs.values_list("asset__project__id", "status")
        status_qs = status_qs.annotate(Count("status"))
        project_statuses = {}

        for project_id, status_value, count in status_qs:
            status_name = Status.CHOICE_MAP[status_value]
            project_statuses.setdefault(project_id, []).append((status_name, count))

        for project in projects:
            project.transcription_statuses = project_statuses.get(project.id, [])
            total_statuses = sum(j for i, j in project.transcription_statuses)
            project.transcription_statuses.insert(
                0, ("Not Started", project.asset_count - total_statuses)
            )


@require_POST
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
    AssetTranscriptionReservation.objects.filter(updated_on__lt=cutoff).delete()

    user_reservation_qs = AssetTranscriptionReservation.objects.filter(
        user=user, asset__pk=asset_pk
    )

    if request.POST.get("release"):
        user_reservation_qs.delete()
        return HttpResponse(status=204)

    # We're relying on the database to meet our integrity requirements and since
    # this is called periodically we want to be fairly fast until we switch to
    # something like Redis.
    #
    # We'll try an UPDATE first since this will be updated regularly as people
    # work and a single operation can handle that. If that fails to match a
    # single record we'll fall back to INSERT and catch the integrity check.

    updated = user_reservation_qs.update(updated_on=timestamp)

    if updated:
        return HttpResponse(status=204)

    try:
        i = AssetTranscriptionReservation(user=user, asset_id=asset_pk)
        i.save()
        return HttpResponse(status=204)
    except IntegrityError:
        return HttpResponse("Another user is currently editing this record", status=409)

