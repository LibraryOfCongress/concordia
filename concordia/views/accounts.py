import logging
import uuid
from smtplib import SMTPException
from typing import Any, Optional, Type

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
from django.forms import Form
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
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
    """
    Confirm a password reset and automatically log in the user.

    Extends Django’s built-in
    [PasswordResetConfirmView](https://docs.djangoproject.com/en/stable/topics/auth/default/#django.contrib.auth.views.PasswordResetConfirmView)
    to use a custom form and enable automatic login after a successful reset.

    Attributes:
        post_reset_login (bool): Whether to log the user in after resetting
            the password.
        form_class (Form): The form used to set the new password and activate
            the account.

    Returns:
        response (HttpResponse): Renders the password reset confirmation page or
            redirects after successful password change and login.
    """

    post_reset_login: bool = True
    form_class: type[Form] = ActivateAndSetPasswordForm


class ConcordiaPasswordResetRequestView(PasswordResetView):
    """
    Request a password reset, supporting inactive users.

    Extends Django’s built-in
    [`PasswordResetView`](https://docs.djangoproject.com/en/stable/topics/auth/default/#django.contrib.auth.views.PasswordResetView)
    to use a custom form that allows inactive users to reset their password
    and activate their account in one step.

    Attributes:
        form_class (Form): The form used to validate and process the password
            reset request.

    Returns:
        response (HttpResponse): Renders the password reset form or redirects
            after successful submission.
    """

    form_class: type[Form] = AllowInactivePasswordResetForm


def registration_rate(group: str, request: HttpRequest) -> Optional[str]:
    """
    Determine the throttling rate for registration attempts.

    Used with the `ratelimit` decorator from `django-ratelimit` to dynamically
    adjust the request rate based on form validation.

    If the submitted registration form is valid, no throttling is applied.
    If it is invalid, the rate is limited to 10 requests per hour.

    Args:
        group (str): The rate limit group name.
        request (HttpRequest): The request containing registration form data.

    Returns:
        rate (str or None): The rate limit string (e.g., "10/h") if the form is
            invalid; otherwise `None` to indicate no throttling.
    """
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
    """
    User registration view with POST-specific rate limiting.

    Extends `django_registration.views.RegistrationView` to apply a POST-specific
    rate limit using the `django-ratelimit` decorator. This protects against
    abuse by restricting failed registration attempts while allowing valid
    submissions to proceed freely.

    Attributes:
        form_class (Form): The form used to collect and validate user registration
            data. Example: `UserRegistrationForm`.

    Returns:
        response (HttpResponse): Renders the registration form or redirects after
            successful registration.
    """

    form_class: Type[Form] = UserRegistrationForm


@method_decorator(never_cache, name="dispatch")
class ConcordiaLoginView(LoginView):
    """
    Login view with Turnstile validation.

    Extends Django's
    [LoginView](https://docs.djangoproject.com/en/stable/topics/auth/default/#django.contrib.auth.views.LoginView)
    to integrate Turnstile validation during POST requests.

    Attributes:
        form_class (Form): The login form used to authenticate users.

    Returns:
        response (HttpResponse): The rendered login form or redirect response,
            depending on the validation outcome.

    Return Behavior:
        - On GET: Renders the login form with the embedded Turnstile widget.
        - On POST:
            - If both login and Turnstile succeed: redirects to the next page.
            - If Turnstile fails: returns the login form with an error message.
            - If the login form is invalid: returns the form with validation errors.
    """

    form_class = UserLoginForm

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
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

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)

        ctx["turnstile_form"] = TurnstileForm(auto_id=False)

        return ctx


@login_required
@never_cache
def account_letter(request: HttpRequest) -> HttpResponse:
    """
    Generate and return a PDF letter summarizing a user's contributions.

    This view creates a service letter for the logged-in user, summarizing their
    transcription and review activity. It uses an HTML template rendered with
    contribution data and converts it to a PDF using WeasyPrint.

    Requires the user to be authenticated.

    Returns:
        response (HttpResponse): A PDF response with content type
            `application/pdf` and a `Content-Disposition` header set to download
            as `letter.pdf`.

    Return Behavior:
        - The generated PDF includes:
            - User's name and join date.
            - Total transcriptions and reviews.
            - List of assets the user contributed to.
    """
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
def get_pages(request: HttpRequest) -> JsonResponse:
    """
    Return a paginated and filtered list of the user's contributed assets as HTML.

    Retrieves assets the current user has worked on, applies pagination, and
    optionally filters by campaign, activity type, status, and date range. Renders
    the results into a fragment of HTML for use in dynamic page updates.

    Requires the user to be authenticated.

    Args:
        request (HttpRequest): The request from the authenticated user.

    Request Parameters:
        - `page` (int): Page number to display. Example: `2`
        - `campaign` (int): Filter by campaign ID. Example: `17`
        - `status` (list[str]): Filter by asset statuses. Example:
          `["in_progress", "submitted"]`
        - `activity` (str): Filter by activity type. Example: `"transcribe"`
        - `order_by` (str): Sort order. Example: `"date-descending"`
        - `start` (str): Start date in YYYY-MM-DD format. Example: `"2023-01-01"`
        - `end` (str): End date in YYYY-MM-DD format. Example: `"2023-12-31"`

    Returns:
        response (JsonResponse): A JSON object containing rendered HTML for recent
            contributed pages.

    Response Format - Success:
        - `content` (str): Rendered HTML for recent pages.

    Example:
        ```json
        {
            "content": "<div class='page-results'>...</div>"
        }
        ```
    """
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
    """
    Display and update user account profile and contribution history.

    Combines functionality from:
    - [LoginRequiredMixin](https://docs.djangoproject.com/en/stable/topics/auth/default/#the-loginrequiredmixin-mixin)
    - [FormView](https://docs.djangoproject.com/en/stable/ref/class-based-views/generic-editing/#formview)
    - [ListView](https://docs.djangoproject.com/en/stable/ref/class-based-views/generic-display/#listview)

    Allows authenticated users to:
    - Update their email address and name
    - View a paginated list of assets they have contributed to
    - See aggregate statistics on their transcription and review activity

    Email changes require confirmation unless the setting
    `REQUIRE_EMAIL_RECONFIRMATION` is False.

    Attributes:
        template_name (str): Template used to render the profile page.
        form_class (Form): Form used to update the user's email address.
        success_url (str): Redirect URL after successful form submission.
        allow_empty (bool): Whether to render the page if the user has no
            contributions.
        paginate_by (int): Number of contributed assets to show per page.
        reconfirmation_email_body_template (str): Path to the plain text email
            body template.
        reconfirmation_email_subject_template (str): Path to the email subject
            template.

    Returns:
        response (HttpResponse): The rendered profile page with contribution data
            or a redirect to `#account` after successful form submission.

    Request Parameters:
        - `page` (int): Page number. Example: `1`
        - `campaign` (int): Campaign filter. Example: `42`
        - `activity` (str): Activity type filter. Example: `"transcribe"`
        - `status` (list[str]): Asset statuses. Example: `["completed"]`
        - `start` (str): Start date in YYYY-MM-DD format. Example: `"2023-01-01"`
        - `end` (str): End date in YYYY-MM-DD format. Example: `"2023-12-31"`
        - `order_by` (str): Sort field. Example: `"date-descending"`
        - `tab` (str): Selected tab. Example: `"account"`
    """

    template_name: str = "account/profile.html"
    form_class: Type[Form] = UserProfileForm
    success_url = reverse_lazy("user-profile")
    reconfirmation_email_body_template: str = "emails/email_reconfirmation_body.txt"
    reconfirmation_email_subject_template: str = (
        "emails/email_reconfirmation_subject.txt"
    )

    # This view will list the assets which the user has contributed to
    # along with their most recent action on each asset. This will be
    # presented in the template as a standard paginated list of Asset
    # instances with annotations
    allow_empty: bool = True
    paginate_by: int = 30

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
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

    def get_queryset(self) -> Any:
        return _get_pages(self.request)

    def get_context_data(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
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

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        initial["email"] = self.request.user.email
        return initial

    def get_form_kwargs(self) -> dict[str, Any]:
        # We'll expose the request object to the form so we can validate that an
        # email is not in use:
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form: Form) -> HttpResponse:
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

    def form_invalid(self, form: Form) -> HttpResponse:
        self.request.session["valid"] = False
        return self.render_to_response(
            self.get_context_data(form=form, active_tab="account")
        )

    def get_success_url(self) -> str:
        # automatically open the Account Settings tab
        return "{}#account".format(super().get_success_url())

    def get_reconfirmation_email_context(self, confirmation_key: str) -> dict[str, Any]:
        return {
            "confirmation_key": confirmation_key,
            "expiration_days": settings.EMAIL_RECONFIRMATION_DAYS,
            "site": get_current_site(self.request),
        }

    def send_reconfirmation_email(self, user: ConcordiaUser) -> None:
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
    """
    Handle user-initiated account deletion.

    Provides a confirmation form for deleting the user's account. If the user has
    contributed transcriptions, their data is anonymized instead of being deleted.
    Otherwise, the account is fully removed. A confirmation email is sent to the
    user's address before deletion. After deletion, the user is logged out.

    Requires the user to be authenticated.

    Attributes:
        template_name (str): Template used to render the confirmation form.
            Example: `"account/account_deletion.html"`
        form_class (Form): Form used to confirm account deletion.
            Example: `AccountDeletionForm`
        success_url (str): URL to redirect to after deletion.
            Example: `"/"`
        email_body_template (str): Template for the body of the confirmation email.
            Example: `"emails/delete_account_body.txt"`
        email_subject_template (str): Template for the subject of the confirmation
            email. Example: `"emails/delete_account_subject.txt"`

    Returns:
        response (HttpResponse): A redirect to the homepage after deletion, or a
            rendered form with errors if validation fails.

    Return Behavior:
        - If the user confirms deletion and has transcriptions: anonymizes their
          account and logs them out.
        - If the user has no transcriptions: deletes the account entirely and logs
          them out.
        - If the form is invalid: re-renders the confirmation form with errors.
    """

    template_name: str = "account/account_deletion.html"
    form_class: Type[Form] = AccountDeletionForm
    success_url: str = reverse_lazy("homepage")
    email_body_template: str = "emails/delete_account_body.txt"
    email_subject_template: str = "emails/delete_account_subject.txt"

    def get_form_kwargs(self) -> dict[str, Any]:
        # We expose the request object to the form so we can use it
        # to log the user out after deletion
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form: Form) -> HttpResponse:
        self.delete_user(form.request.user, form.request)
        return super().form_valid(form)

    def delete_user(self, user: ConcordiaUser, request: HttpRequest) -> None:
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

    def send_deletion_email(self, email: str) -> None:
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
    """
    Handle email reconfirmation via a signed URL token.

    Validates a confirmation key sent to the user's new email address during
    an address change. If valid and not expired, applies the email update. If
    invalid, expired, or mismatched, renders an error message.

    Attributes:
        template_name (str): Template rendered if the confirmation fails.
            Example: `"account/email_reconfirmation_failed.html"`
        success_url (str): URL to redirect to on success.
            Example: `"/accounts/profile/#account"`
        BAD_USERNAME_MESSAGE (str): Error if the user account cannot be found.
        BAD_EMAIL_MESSAGE (str): Error if the email does not match expectations.
        EXPIRED_MESSAGE (str): Error if the key is expired.
        INVALID_KEY_MESSAGE (str): Error if the key signature is invalid.

    Returns:
        response (HttpResponse): Redirects to the profile page with `#account`
            on success, or renders the failure template with error details.

    URL Parameters:
        confirmation_key (str): A signed token containing the username and new
            email. Example: `"ZHVtbXl1c2VyOnNvbWVvbmVAZXhhbXBsZS5jb20="`
    """

    success_url = reverse_lazy("user-profile")
    template_name = "account/email_reconfirmation_failed.html"

    BAD_USERNAME_MESSAGE: str = _("The account you attempted to confirm is invalid.")
    BAD_EMAIL_MESSAGE: str = _("The email you attempted to confirm is invalid.")
    EXPIRED_MESSAGE: str = _(
        "The confirmation key you provided is expired. Email confirmation links "
        "expire after 7 days. If your key is expired, you will need to re-enter "
        "your new email address"
    )
    INVALID_KEY_MESSAGE: str = _(
        "The confirmation key you provided is invalid. Email confirmation links "
        "expire after 7 days. If your key is expired, you will need to re-enter "
        "your new email address."
    )

    def get_success_url(self) -> str:
        return "{}#account".format(self.success_url)

    def get(self, *args: Any, **kwargs: Any) -> HttpResponse:
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

    def confirm(self, *args: Any, **kwargs: Any) -> ConcordiaUser:
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

    def validate_key(self, confirmation_key: str) -> tuple[str, str]:
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

    def get_user(self, username: str) -> ConcordiaUser:
        try:
            user = ConcordiaUser.objects.get(username=username)
            return user
        except ConcordiaUser.DoesNotExist as exc:
            raise ValidationError(
                self.BAD_USERNAME_MESSAGE, code="bad_username"
            ) from exc
