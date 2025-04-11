import logging
import uuid
from smtplib import SMTPException

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
from django.contrib.sites.shortcuts import get_current_site
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect
from django.template import loader
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache
from django.views.generic import FormView, ListView, TemplateView
from django_ratelimit.decorators import ratelimit
from django_registration.backends.activation.views import RegistrationView
from weasyprint import HTML

from concordia.forms import (
    AccountDeletionForm,
    ActivateAndSetPasswordForm,
    AllowInactivePasswordResetForm,
    TurnstileForm,
    UserLoginForm,
    UserNameForm,
    UserProfileForm,
    UserRegistrationForm,
)
from concordia.models import Campaign, ConcordiaUser, UserProfileActivity

from .utils import _get_pages

logger = logging.getLogger(__name__)


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
