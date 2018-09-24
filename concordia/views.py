import html
import json
import os
import time
from datetime import datetime
from logging import getLogger
from warnings import warn

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import Http404, get_object_or_404, redirect, render
from django.template import loader
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.generic import DetailView, FormView, ListView, TemplateView, View
from registration.backends.hmac.views import RegistrationView
from rest_framework import generics, status
from rest_framework.test import APIRequestFactory

from concordia.forms import (AssetFilteringForm, CaptchaEmbedForm,
                             ConcordiaContactUsForm, ConcordiaUserEditForm,
                             ConcordiaUserForm)
from concordia.models import (Asset, Campaign, Item, Project, Status, Transcription,
                              UserProfile)
from concordia.views_ws import PageInUseCreate

logger = getLogger(__name__)

ASSETS_PER_PAGE = 36
PROJECTS_PER_PAGE = 36
ITEMS_PER_PAGE = 36


def concordia_api(relative_path):
    warn(
        f"Internal API call for {relative_path} should be refactored",
        category=DeprecationWarning,
    )
    abs_path = "{}/api/v1/{}".format(settings.CONCORDIA["netloc"], relative_path)
    logger.debug("Calling API path %s", abs_path)
    data = requests.get(abs_path).json()

    logger.debug("Received %s", data)
    return data


def get_anonymous_user(request, user_id=True):
    """
    Get the user called "anonymous" if it exist. Create the user if it doesn't exist
    This is the default concordia user if someone is working on the site without logging in first.

    :parameter: request django request object
    :parameter: user_id Boolean defaults to True, if true returns user id, otherwise return user object
    :return: User id or User
    """
    response = requests.get(
        "%s://%s/ws/anonymous_user/" % (request.scheme, request.get_host()),
        cookies=request.COOKIES,
    )
    anonymous_json_val = json.loads(response.content.decode("utf-8"))
    if user_id:
        return anonymous_json_val["id"]
    else:
        return anonymous_json_val


@never_cache
def healthz(request):
    status = {"current_time": time.time(), "load_average": os.getloadavg()}

    # We don't want to query a large table but we do want to hit the database
    # at last once:
    status["database_has_data"] = Campaign.objects.count() > 0

    return HttpResponse(content=json.dumps(status), content_type="application/json")


class ConcordiaRegistrationView(RegistrationView):
    form_class = ConcordiaUserForm


class AccountProfileView(LoginRequiredMixin, TemplateView):
    template_name = "profile.html"

    def post(self, *args, **kwargs):
        instance = get_object_or_404(User, pk=self.request.user.id)
        form = ConcordiaUserEditForm(
            self.request.POST, self.request.FILES, instance=instance
        )
        if form.is_valid():
            obj = form.save(commit=True)
            obj.id = self.request.user.id
            if (
                "password1" not in self.request.POST
                and "password2" not in self.request.POST
            ):
                obj.password = self.request.user.password
            else:
                update_session_auth_hash(self.request, obj)
            obj.save()

            if "myfile" in self.request.FILES:
                myfile = self.request.FILES["myfile"]
                profile, created = UserProfile.objects.update_or_create(
                    user=obj, defaults={"myfile": myfile}
                )

            messages.success(self.request, "User profile information changed!")
        else:
            messages.error(self.request, form.errors)
            return HttpResponseRedirect("/account/profile/")
        return redirect(reverse("user-profile"))

    def get_context_data(self, **kws):
        last_name = self.request.user.last_name
        if last_name:
            last_name = " " + last_name
        else:
            last_name = ""

        data = {
            "username": self.request.user.username,
            "email": self.request.user.email,
            "first_name": self.request.user.first_name + last_name,
        }

        response = requests.get(
            "%s://%s/ws/user_profile/%s/"
            % (self.request.scheme, self.request.get_host(), self.request.user.id),
            cookies=self.request.COOKIES,
        )
        user_profile_json_val = json.loads(response.content.decode("utf-8"))

        if "myfile" in user_profile_json_val:
            data["myfile"] = user_profile_json_val["myfile"]

        response = requests.get(
            "%s://%s/ws/transcription_by_user/%s/"
            % (self.request.scheme, self.request.get_host(), self.request.user.id),
            cookies=self.request.COOKIES,
        )

        transcription_json_val = json.loads(response.content.decode("utf-8"))

        for trans in transcription_json_val["results"]:
            campaign_response = requests.get(
                "%s://%s/ws/campaign_by_id/%s/"
                % (
                    self.request.scheme,
                    self.request.get_host(),
                    trans["asset"]["campaign"]["id"],
                ),
                cookies=self.request.COOKIES,
            )
            trans["campaign_name"] = json.loads(
                campaign_response.content.decode("utf-8")
            )["slug"]
            trans["updated_on"] = datetime.strptime(
                trans["updated_on"], "%Y-%m-%dT%H:%M:%S.%fZ"
            )

        return super().get_context_data(
            **dict(
                kws,
                transcriptions=transcription_json_val["results"],
                form=ConcordiaUserEditForm(initial=data),
            )
        )


class ConcordiaView(TemplateView):
    template_name = "transcriptions/campaigns.html"

    def get_context_data(self, **kws):
        response = concordia_api("campaigns/")
        return dict(super().get_context_data(**kws), response=response)


class ConcordiaCampaignView(TemplateView):
    template_name = "transcriptions/campaign.html"

    def get_context_data(self, **kws):
        from .serializers import CampaignDetailSerializer

        campaign = get_object_or_404(Campaign, slug=self.args[0])

        serialized = CampaignDetailSerializer(campaign).data

        for sub_col in serialized["projects"]:
            sub_col["campaign"] = campaign

        project_sorted_list = sorted(serialized["projects"], key=lambda k: (k["title"]))

        return dict(
            super().get_context_data(**kws),
            campaign=serialized,
            projects=project_sorted_list,
        )


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
            item_qs = item_qs.exclude(visible=False)

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
        item_qs = Item.objects.select_related("project", "project__campaign")

        if not self.request.user.is_staff:
            item_qs = item_qs.filter(visible=True)

        self.item = get_object_or_404(
            item_qs,
            campaign__slug=self.kwargs["campaign_slug"],
            project__slug=self.kwargs["project_slug"],
            slug=self.kwargs["slug"],
        )

        asset_qs = self.item.asset_set.all()
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
                "campaign": self.item.campaign,
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
            item__slug=self.kwargs["item_slug"],
            item__project__slug=self.kwargs["project_slug"],
            item__project__campaign__slug=self.kwargs["campaign_slug"],
            slug=self.kwargs["slug"],
        )
        asset_qs = asset_qs.select_related("item__project__campaign")

        return asset_qs

    def get_asset_list_json(self):
        """
        make a call to the REST web service to assets for a campaign
        :return: json of the assets
        """
        response = requests.get(
            "%s://%s/ws/asset/%s/"
            % (self.request.scheme, self.request.get_host(), self.args[0]),
            cookies=self.request.COOKIES,
        )
        return json.loads(response.content.decode("utf-8"))

    def submitted_page(self, url, asset_json):
        """
        when the transcription state is SUBMITTED, return a page that does not have a transcription started.
        If all pages are started, return the url passed in
        :param url: default url to return
        :param asset_json: Unused, needed to make function signature match completed_page
        :return: url of next page
        """
        return_path = url

        # find a page with no transcriptions in this campaign

        asset_list_json = self.get_asset_list_json()

        for asset_item in asset_list_json["results"]:
            response = requests.get(
                "%s://%s/ws/transcription/%s/"
                % (self.request.scheme, self.request.get_host(), asset_item["id"]),
                cookies=self.request.COOKIES,
            )
            transcription_json = json.loads(response.content.decode("utf-8"))
            if transcription_json["text"] == "":
                return_path = "/campaigns/%s/asset/%s/" % (
                    self.args[0],
                    asset_item["slug"],
                )
                break

        return return_path

    def completed_page(self, url, asset_json):
        """
        when the transcription state is COMPLETED, return the next page in sequence that needs work
        If all pages are completed, return the url passed in
        :param url: default url to return
        :param asset_json: json representation of the asset
        :return: url of next page
        """
        return_path = url

        asset_list_json = self.get_asset_list_json()

        def get_transcription(asset_item):
            response = requests.get(
                "%s://%s/ws/transcription/%s/"
                % (self.request.scheme, self.request.get_host(), asset_item["id"]),
                cookies=self.request.COOKIES,
            )
            return json.loads(response.content.decode("utf-8"))

        for asset_item in asset_list_json["results"][asset_json["sequence"] :]:
            transcription_json = get_transcription(asset_item)
            if transcription_json["status"] != Status.COMPLETED:
                return_path = "/campaigns/%s/asset/%s/" % (
                    self.args[0],
                    asset_item["slug"],
                )
                break

        # no asset found, iterate the asset_list_json from beginning to this asset's sequence
        if return_path == url:
            for asset_item in asset_list_json["results"][: asset_json["sequence"]]:
                transcription_json = get_transcription(asset_item)
                if transcription_json["status"] != Status.COMPLETED:
                    return_path = "/campaigns/%s/asset/%s/" % (
                        self.args[0],
                        asset_item["slug"],
                    )
                    break

        return return_path

    def check_page_in_use(self, url, user):
        """
        Check the page in use for the asset, return true if in use within the last 5 minutes, otherwise false
        :param url: url to test if in use
        :param user: user object
        :return: True or False
        """
        response = requests.get(
            "%s://%s/ws/page_in_use_count/%s/%s/"
            % (self.request.scheme, self.request.get_host(), user, url),
            cookies=self.request.COOKIES,
        )
        json_val = json.loads(response.content.decode("utf-8"))

        return json_val["page_in_use"]

    def get_context_data(self, **kwargs):
        """
        Handle the GET request
        :param kws:
        :return: dictionary of items used in the template
        """

        ctx = super().get_context_data(**kwargs)
        asset = ctx['asset']
        ctx['item'] = item = asset.item
        ctx['project'] = project = item.project
        ctx['campaign'] = project.campaign

        in_use_url = reverse(
            "transcriptions:asset-detail",
            kwargs={
                "campaign_slug": self.kwargs["campaign_slug"],
                "project_slug": self.kwargs["project_slug"],
                "item_slug": self.kwargs["item_slug"],
                "slug": self.kwargs["slug"],
            },
        )

        current_user_id = (
            self.request.user.id
            if self.request.user.id is not None
            else get_anonymous_user(self.request)
        )

        page_in_use = self.check_page_in_use(in_use_url, current_user_id)

        discussion_hide = True

        # Get all transcriptions, they are no longer tied to a specific user
        response = requests.get(
            "%s://%s/ws/transcription/%s/"
            % (self.request.scheme, self.request.get_host(), asset.id),
            cookies=self.request.COOKIES,
        )
        transcription_json = json.loads(response.content.decode("utf-8"))

        response = requests.get(
            "%s://%s/ws/tags/%s/"
            % (self.request.scheme, self.request.get_host(), asset.id),
            cookies=self.request.COOKIES,
        )
        json_tags = []
        if response.status_code == status.HTTP_200_OK:
            json_tags_response = json.loads(response.content.decode("utf-8"))
            for json_tag in json_tags_response["results"]:
                json_tags.append(json_tag["value"])

        captcha_form = CaptchaEmbedForm()

        response = requests.get(
            "%s://%s/ws/page_in_use_user/%s/%s/"
            % (
                self.request.scheme,
                self.request.get_host(),
                current_user_id,
                in_use_url,
            ),
            cookies=self.request.COOKIES,
        )
        page_in_use_json = json.loads(response.content.decode("utf-8"))

        if page_in_use_json["user"] is None:
            same_page_count_for_this_user = 0
        else:
            same_page_count_for_this_user = 1

        page_dict = {
            "page_url": in_use_url,
            "user": current_user_id,
            "updated_on": datetime.now(),
        }

        if page_in_use is False and same_page_count_for_this_user == 0:
            # add this page as being in use by this user
            # call the web service which will use the serializer to insert the value.
            # this takes care of deleting old entries in PageInUse table

            factory = APIRequestFactory()
            request = factory.post("/ws/page_in_use%s/" % (in_use_url,), page_dict)
            request.session = self.request.session

            PageInUseCreate.as_view()(request)
        elif same_page_count_for_this_user == 1:
            # update the PageInUse
            change_page_in_use = {"page_url": in_use_url, "user": current_user_id}

            requests.put(
                "%s://%s/ws/page_in_use_update/%s/%s/"
                % (
                    self.request.scheme,
                    self.request.get_host(),
                    current_user_id,
                    in_use_url,
                ),
                data=change_page_in_use,
                cookies=self.request.COOKIES,
            )

        if self.request.user.is_anonymous:
            ctx[
                "is_anonymous_user_captcha_validated"
            ] = self.is_anonymous_user_captcha_validated()

        ctx.update(
            {
                "page_in_use": page_in_use,
                "transcription": transcription_json,
                "tags": json_tags,
                "captcha_form": captcha_form,
                "discussion_hide": discussion_hide,
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

    def post(self, *args, **kwargs):
        """
        Handle POST from campaigns page for individual asset
        :param args:
        :param kwargs:
        :return: redirect back to same page
        """
        # don't know why this would be called here
        # self.get_context_data()

        if self.request.POST.get("action").lower() == "contact a manager":
            return redirect(reverse("contact") + "?pre_populate=true")

        response = requests.get(
            "%s://%s/ws/asset_by_slug/%s/%s/"
            % (
                self.request.scheme,
                self.request.get_host(),
                self.args[0],
                self.args[1],
            ),
            cookies=self.request.COOKIES,
        )
        asset_json = json.loads(response.content.decode("utf-8"))

        if self.request.user.is_anonymous and not (
            self.is_anonymous_user_captcha_validated()
        ):
            captcha_form = CaptchaEmbedForm(self.request.POST)
            if not captcha_form.is_valid():
                logger.info("Invalid captcha response")
                messages.error(self.request, "Invalid Captcha.")
                return self.get(self.request, *args, **kwargs)
            else:
                self.request.session[
                    "captcha_validated_at"
                ] = datetime.now().timestamp()

        redirect_path = self.request.path

        if "tx" in self.request.POST and "tagging" not in self.request.POST:
            tx = self.request.POST.get("tx")
            tx_status = self.state_dictionary[self.request.POST.get("action")]
            requests.post(
                "%s://%s/ws/transcription_create/"
                % (self.request.scheme, self.request.get_host()),
                data={
                    "asset": asset_json["id"],
                    "user_id": self.request.user.id
                    if self.request.user.id is not None
                    else get_anonymous_user(self.request),
                    "status": tx_status,
                    "text": tx,
                },
                cookies=self.request.COOKIES,
            )

            # dictionary to pick which function should return the next page on a POST submit
            next_page_dictionary = {
                Status.EDIT: lambda x, y: x,
                Status.SUBMITTED: self.submitted_page,
                Status.COMPLETED: self.completed_page,
            }

            if tx_status == Status.EDIT:
                messages.success(
                    self.request, "The transcription was saved successfully."
                )
            elif tx_status == Status.SUBMITTED:
                messages.success(self.request, "The transcription is ready for review.")
            elif tx_status == Status.COMPLETED:
                messages.success(self.request, "The transcription is completed.")

            redirect_path = next_page_dictionary[tx_status](redirect_path, asset_json)

        elif "tags" in self.request.POST and self.request.user.is_authenticated:
            tags = self.request.POST.get("tags").split(",")
            # get existing tags
            response = requests.get(
                "%s://%s/ws/tags/%s/"
                % (self.request.scheme, self.request.get_host(), asset_json["id"]),
                cookies=self.request.COOKIES,
            )
            existing_tags_json_val = json.loads(response.content.decode("utf-8"))
            existing_tags_list = []
            for tag_dict in existing_tags_json_val["results"]:
                existing_tags_list.append(tag_dict["value"])

            for tag in tags:
                response = requests.post(
                    "%s://%s/ws/tag_create/"
                    % (self.request.scheme, self.request.get_host()),
                    data={
                        "campaign": asset_json["campaign"]["slug"],
                        "asset": asset_json["slug"],
                        "user_id": self.request.user.id
                        if self.request.user.id is not None
                        else get_anonymous_user(self.request),
                        "name": tag,
                        "value": tag,
                    },
                    cookies=self.request.COOKIES,
                )

                # keep track of existing tags so we can remove deleted tags
                if tag in existing_tags_list:
                    existing_tags_list.remove(tag)

            # delete "old" tags
            for old_tag in existing_tags_list:
                response = requests.delete(
                    "%s://%s/ws/tag_delete/%s/%s/%s/%s/"
                    % (
                        self.request.scheme,
                        self.request.get_host(),
                        self.args[0],
                        self.args[1],
                        old_tag,
                        self.request.user.id,
                    ),
                    cookies=self.request.COOKIES,
                )

            redirect_path += "#tab-tag"

            messages.success(self.request, "Tags have been saved.")

        return redirect(redirect_path)


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


class ConcordiaPageInUse(View):
    """
    Class to handle AJAX calls from the transcription page
    """

    def post(self, *args, **kwargs):
        """
        handle the post request from the periodic AJAX call from the transcription page
        The primary purpose is to update the entry in PageInUse
        :param args:
        :param kwargs:
        :return: "ok"
        """

        if self.request.is_ajax():
            json_dict = json.loads(self.request.body)
            user_name = json_dict["user"]
            page_url = json_dict["page_url"]
        else:
            user_name = self.request.POST.get("user", None)
            page_url = self.request.POST.get("page_url", None)

        if user_name == "AnonymousUser":
            user_name = "anonymous"

        if user_name and page_url:
            response = requests.get(
                "%s://%s/ws/user/%s/"
                % (self.request.scheme, self.request.get_host(), user_name),
                cookies=self.request.COOKIES,
            )
            user_json_val = json.loads(response.content.decode("utf-8"))

            # update the PageInUse

            change_page_in_use = {"page_url": page_url, "user": user_json_val["id"]}

            requests.put(
                "%s://%s/ws/page_in_use_update/%s/%s/"
                % (
                    self.request.scheme,
                    self.request.get_host(),
                    user_json_val["id"],
                    page_url,
                ),
                data=change_page_in_use,
                cookies=self.request.COOKIES,
            )

        return HttpResponse("ok")


class TranscriptionView(TemplateView):
    # TODO: Is this class still used??
    template_name = "transcriptions/transcription.html"

    def get_context_data(self, **kws):
        transcription = Transcription.objects.get(id=self.args[0])
        transcription_user = get_user_model().objects.get(id=transcription.id)
        return super().get_context_data(
            **dict(
                kws, transcription=transcription, transcription_user=transcription_user
            )
        )


class ToDoView(TemplateView):
    template_name = "todo.html"


class ContactUsView(FormView):
    template_name = "contact.html"
    form_class = ConcordiaContactUsForm

    def get_context_data(self, *args, **kwargs):
        res = super().get_context_data(*args, **kwargs)
        res["title"] = "Contact Us"
        return res

    def get_initial(self):
        if self.request.GET.get("pre_populate", None) is None:
            return None
        else:
            return {
                "email": (
                    None if self.request.user.is_anonymous else self.request.user.email
                ),
                "link": (
                    self.request.META.get("HTTP_REFERER")
                    if self.request.META.get("HTTP_REFERER")
                    else None
                ),
            }

    def post(self, *args, **kwargs):
        email = html.escape(self.request.POST.get("email") or "")
        subject = html.escape(self.request.POST.get("subject") or "")
        category = html.escape(self.request.POST.get("category") or "")
        link = html.escape(self.request.POST.get("link") or "")
        story = html.escape(self.request.POST.get("story") or "")

        t = loader.get_template("emails/contact_us_email.txt")
        send_mail(
            subject,
            t.render(
                {
                    "from_email": email,
                    "subject": subject,
                    "category": category,
                    "link": link,
                    "story": story,
                }
            ),
            getattr(settings, "DEFAULT_FROM_EMAIL"),
            [getattr(settings, "DEFAULT_TO_EMAIL")],
            fail_silently=True,
        )

        messages.success(self.request, "Your contact message has been sent...")

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


class DeleteCampaignView(TemplateView):
    """
    deletes the campaign
    """

    def get(self, request, *args, **kwargs):
        """
        GET request to delete a collection. Only allow admin access
        :param request:
        :param args:
        :param kwargs:
        :return: redirect to home (/) or redirect to /campaigns/
        """
        if not self.request.user.is_superuser:
            return HttpResponseRedirect("/")
        else:
            requests.delete(
                "%s://%s/ws/campaign_delete/%s/"
                % (self.request.scheme, self.request.get_host(), self.args[0]),
                cookies=self.request.COOKIES,
            )
            # FIXME: this needs error handling or being replaced outright (and has never been tested)
            os.system(
                "rm -rf {0}".format(
                    settings.MEDIA_ROOT + "/concordia/" + collection.slug
                )
            )
            return redirect("/campaigns/")


class DeleteAssetView(TemplateView):
    """
    Hides an asset with status inactive. Hidden assets do not display in
    asset view. After hiding an asset, page redirects to campaign view.
    """

    def get(self, request, *args, **kwargs):
        """
        GET request to delete an asset. Only allow admin access
        :param request:
        :param args:
        :param kwargs:
        :return: redirect to home (/) or redirect to /campaigns
        :return:
        """
        if not self.request.user.is_superuser:
            return HttpResponseRedirect("/")
        else:
            asset_update = {"campaign": self.args[0], "slug": self.args[1]}

            requests.put(
                "%s://%s/ws/asset_update/%s/%s/"
                % (
                    self.request.scheme,
                    self.request.get_host(),
                    self.args[0],
                    self.args[1],
                ),
                data=asset_update,
                cookies=self.request.COOKIES,
            )
            return redirect("/campaigns/" + self.args[0] + "/")


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
                "asset__userassettagcollection__user_id", distinct=True
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


class FilterCampaigns(generics.ListAPIView):
    def get_queryset(self):
        name_query = self.request.query_params.get("name")
        if name_query:
            queryset = Campaign.objects.filter(slug__contains=name_query).values_list(
                "slug", flat=True
            )
        else:
            queryset = Campaign.objects.all().values_list("slug", flat=True)
        return queryset

    def list(self, request):
        queryset = self.get_queryset()
        from django.http import JsonResponse

        return JsonResponse(list(queryset), safe=False)


def publish_campaign(request, campaign, is_publish):
    """ Publish/Unpublish a campaign to otherr users. On un/publishing campaign,
    it will get does the same effect for all its projects. """

    try:
        campaign = Campaign.objects.get(slug=campaign)
    except Campaign.DoesNotExist:
        raise Http404

    if is_publish == "true":
        campaign.is_publish = True
    else:
        campaign.is_publish = False

    projects = campaign.project_set.all()

    for sc in projects:
        sc.is_publish = True if is_publish == "true" else False
        sc.save()

    campaign.save()

    return JsonResponse(
        {
            "message": "Campaign has been %s."
            % ("published" if is_publish == "true" else "unpublished"),
            "state": True if is_publish == "true" else False,
        },
        safe=True,
    )


def publish_project(request, campaign, project, is_publish):
    """ Publish/Unpublish a project to other users. """

    try:
        project = Project.objects.get(campaign__slug=campaign, slug=project)
    except Project.DoesNotExist:
        raise Http404

    if is_publish == "true":
        project.is_publish = True
    else:
        project.is_publish = False

    project.save()

    return JsonResponse(
        {
            "message": "Project has been %s."
            % ("published" if is_publish == "true" else "unpublished"),
            "state": True if is_publish == "true" else False,
        },
        safe=True,
    )


class DeleteProjectView(TemplateView):
    """
    deletes the project
    """

    def get(self, request, *args, **kwargs):
        collection = Campaign.objects.get(slug=self.args[0])
        subcollection = Project.objects.get(slug=self.args[1])
        subcollection.asset_set.all().delete()
        subcollection.delete()
        os.system(
            "rm -rf {0}".format(
                settings.MEDIA_ROOT
                + "/concordia/"
                + collection.slug
                + "/"
                + subcollection.slug
            )
        )
        return redirect("/campaigns/" + collection.slug + "/")
