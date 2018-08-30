import html
import json
import os
from datetime import datetime, timedelta
from logging import getLogger

import requests
from captcha.fields import CaptchaField
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import Http404, get_object_or_404, redirect, render
from django.template import loader
from django.urls import reverse
from django.views.generic import FormView, TemplateView, View
from registration.backends.simple.views import RegistrationView
from rest_framework import status, generics
from rest_framework.test import APIRequestFactory

from concordia.forms import (CaptchaEmbedForm, ConcordiaContactUsForm,
                             ConcordiaUserEditForm, ConcordiaUserForm)
from concordia.models import (Asset, Collection, PageInUse, Status, Transcription,
                              UserProfile)
from concordia.views_ws import PageInUseCreate
from importer.views import CreateCollectionView

logger = getLogger(__name__)

ASSETS_PER_PAGE = 36
PROJECTS_PER_PAGE = 36


def concordia_api(relative_path):
    abs_path = "{}/api/v1/{}".format(settings.CONCORDIA["netloc"], relative_path)
    logger.debug("Calling API path %s", abs_path)
    data = requests.get(abs_path).json()

    logger.debug("Received %s", data)
    return data


def get_anonymous_user(user_id=True):
    """
    Get the user called "anonymous" if it exist. Create the user if it doesn't exist
    This is the default concordia user if someone is working on the site without logging in first.
    :parameter: user_id Boolean defaults to True, if true returns user id, otherwise return user object
    :return: User id or User
    """
    anon_user = User.objects.filter(username="anonymous").first()
    if anon_user is None:
        anon_user = User.objects.create_user(
            username="anonymous",
            email="anonymous@anonymous.com",
            password="concanonymous",
        )
    if user_id:
        return anon_user.id
    else:
        return anon_user


class ConcordiaRegistrationView(RegistrationView):
    form_class = ConcordiaUserForm


class AccountProfileView(LoginRequiredMixin, TemplateView):
    template_name = "profile.html"

    def post(self, *args, **kwargs):
        context = self.get_context_data()
        instance = get_object_or_404(User, pk=self.request.user.id)
        form = ConcordiaUserEditForm(
            self.request.POST, self.request.FILES, instance=instance
        )
        if form.is_valid():
            obj = form.save(commit=True)
            obj.id = self.request.user.id
            if (
                not self.request.POST["password1"]
                and not self.request.POST["password2"]
            ):
                obj.password = self.request.user.password
            obj.save()

            if "myfile" in self.request.FILES:
                myfile = self.request.FILES["myfile"]
                profile, created = UserProfile.objects.update_or_create(
                    user=obj, defaults={"myfile": myfile}
                )
        else:
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
        profile = UserProfile.objects.filter(user=self.request.user)
        if profile:
            data["myfile"] = profile[0].myfile

        response = requests.get(
            "%s://%s/ws/transcription_by_user/%s/"
            % (self.request.scheme, self.request.get_host(), self.request.user.id),
            cookies=self.request.COOKIES,
        )

        transcription_json_val = json.loads(response.content.decode("utf-8"))

        for trans in transcription_json_val["results"]:
            collection_response = requests.get(
                "%s://%s/ws/collection_by_id/%s/"
                % (
                    self.request.scheme,
                    self.request.get_host(),
                    trans["asset"]["collection"]["id"],
                ),
                cookies=self.request.COOKIES,
            )
            trans["collection_name"] = json.loads(
                collection_response.content.decode("utf-8")
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
    template_name = "transcriptions/home.html"

    def get_context_data(self, **kws):
        response = concordia_api("collections/")
        return dict(super().get_context_data(**kws), response=response)


class ConcordiaProjectView(TemplateView):
    template_name = "transcriptions/project.html"

    def get_context_data(self, **kws):

        response = requests.get(
            "%s://%s/ws/collection/%s/"
            % (self.request.scheme, self.request.get_host(), self.args[0]),
            cookies=self.request.COOKIES,
        )
        collection_json_val = json.loads(response.content.decode("utf-8"))
        for sub_col in collection_json_val["subcollections"]:
            sub_col["collection"] = collection_json_val

        project_sorted_list = sorted(
            collection_json_val["subcollections"], key=lambda k: (k["title"])
        )

        paginator = Paginator(project_sorted_list, ASSETS_PER_PAGE)

        if not self.request.GET.get("page"):
            page = 1
        else:
            page = self.request.GET.get("page")

        projects = paginator.get_page(page)

        return dict(
            super().get_context_data(**kws), collection=collection_json_val, projects=projects
        )


class ConcordiaCollectionView(TemplateView):
    template_name = "transcriptions/collection.html"

    def get_context_data(self, **kws):

        response = requests.get(
            "%s://%s/ws/collection/%s/"
            % (self.request.scheme, self.request.get_host(), self.args[0]),
            cookies=self.request.COOKIES,
        )
        collection_json_val = json.loads(response.content.decode("utf-8"))
        asset_sorted_list = sorted(
            collection_json_val["assets"], key=lambda k: (k["slug"])
        )

        paginator = Paginator(asset_sorted_list, ASSETS_PER_PAGE)

        if not self.request.GET.get("page"):
            page = 1
        else:
            page = self.request.GET.get("page")

        assets = paginator.get_page(page)

        return dict(
            super().get_context_data(**kws),
            collection=collection_json_val,
            assets=assets,
        )


class ConcordiaAssetView(TemplateView):
    """
    Class to handle GET ansd POST requests on route /transcribe/<collection>/asset/<asset>
    """

    template_name = "transcriptions/asset.html"

    state_dictionary = {
        "Save": Status.EDIT,
        "Submit for Review": Status.SUBMITTED,
        "Mark Completed": Status.COMPLETED,
    }

    def get_asset_list_json(self):
        """
        make a call to the REST web service to assets for a collection
        :return: json of the assets
        """
        response = requests.get(
            "%s://%s/ws/asset/%s/"
            % (
                self.request.scheme,
                self.request.get_host(),
                self.args[0]),
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

        # find a page with no transcriptions in this collection

        asset_list_json = self.get_asset_list_json()

        for asset_item in asset_list_json["results"]:
            response = requests.get(
                "%s://%s/ws/transcription/%s/"
                % (self.request.scheme, self.request.get_host(), asset_item["id"]),
                cookies=self.request.COOKIES,
            )
            transcription_json = json.loads(response.content.decode("utf-8"))
            if transcription_json["text"] == "":
                return_path = "/transcribe/%s/asset/%s/" % (self.args[0], asset_item["slug"])
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

        for asset_item in asset_list_json["results"][asset_json["sequence"]:]:
            transcription_json = get_transcription(asset_item)
            if transcription_json["status"] != Status.COMPLETED:
                return_path = "/transcribe/%s/asset/%s/" % (self.args[0], asset_item["slug"])
                break

        # no asset found, iterate the asset_list_json from beginning to this asset's sequence
        if return_path == url:
            for asset_item in asset_list_json["results"][:asset_json["sequence"]]:
                transcription_json = get_transcription(asset_item)
                if transcription_json["status"] != Status.COMPLETED:
                    return_path = "/transcribe/%s/asset/%s/" % (self.args[0], asset_item["slug"])
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

    def get_context_data(self, **kws):
        """
        Handle the GET request
        :param kws:
        :return: dictionary of items used in the template
        """
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

        in_use_url = "/transcribe/%s/asset/%s/" % (
            asset_json["collection"]["slug"],
            asset_json["slug"],
        )
        current_user_id = (
            self.request.user.id
            if self.request.user.id is not None
            else get_anonymous_user()
        )
        page_in_use = self.check_page_in_use(in_use_url, current_user_id)

        # Get all transcriptions, they are no longer tied to a specific user

        response = requests.get(
            "%s://%s/ws/transcription/%s/"
            % (self.request.scheme, self.request.get_host(), asset_json["id"]),
            cookies=self.request.COOKIES,
        )
        transcription_json = json.loads(response.content.decode("utf-8"))

        response = requests.get(
            "%s://%s/ws/tags/%s/"
            % (self.request.scheme, self.request.get_host(), asset_json["id"]),
            cookies=self.request.COOKIES,
        )
        json_tags = []
        if response.status_code == status.HTTP_200_OK:
            json_tags_response = json.loads(response.content.decode("utf-8"))
            for json_tag in json_tags_response["results"]:
                json_tags.append(json_tag["value"])

        captcha_form = CaptchaEmbedForm()

        response = requests.get(
            "%s://%s/ws/page_in_use_user/%s/%s/" %
            (
                self.request.scheme,
                self.request.get_host(),
                current_user_id,
                in_use_url
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
                "%s://%s/ws/page_in_use_update/%s/%s/" %
                (

                    self.request.scheme,
                    self.request.get_host(),
                    current_user_id,
                    in_use_url
                ),
                data=change_page_in_use,
                cookies=self.request.COOKIES,
            )

        return dict(
            super().get_context_data(**kws),
            page_in_use=page_in_use,
            asset=asset_json,
            transcription=transcription_json,
            tags=json_tags,
            captcha_form=captcha_form,
        )

    def post(self, *args, **kwargs):
        """
        Handle POST from transcribe page for individual asset
        :param args:
        :param kwargs:
        :return: redirect back to same page
        """
        # don't know why this would be called here
        # self.get_context_data()

        if self.request.POST.get("action").lower() == 'contact manager':
            return redirect(reverse('contact') + "?pre_populate=true")

        if self.request.user.is_anonymous:
            captcha_form = CaptchaEmbedForm(self.request.POST)
            if not captcha_form.is_valid():
                logger.info("Invalid captcha response")
                return self.get(self.request, *args, **kwargs)

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

        redirect_path = self.request.path

        if "tx" in self.request.POST:
            tx = self.request.POST.get("tx")
            tx_status = self.state_dictionary[self.request.POST.get("action")]
            requests.post(
                "%s://%s/ws/transcription_create/"
                % (self.request.scheme, self.request.get_host()),
                data={
                    "asset": asset_json["id"],
                    "user_id": self.request.user.id
                    if self.request.user.id is not None
                    else get_anonymous_user(),
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

            redirect_path = next_page_dictionary[tx_status](redirect_path, asset_json)

        if "tags" in self.request.POST and self.request.user.is_authenticated == True:
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
                        "collection": asset_json["collection"]["slug"],
                        "asset": asset_json["slug"],
                        "user_id": self.request.user.id
                        if self.request.user.id is not None
                        else get_anonymous_user(),
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
                response = requests.delete("%s://%s/ws/tag_delete/%s/%s/%s/%s/" %
                                           (self.request.scheme,
                                            self.request.get_host(),
                                            self.args[0],
                                            self.args[1],
                                            old_tag,
                                            self.request.user.id),
                                           cookies=self.request.COOKIES)

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
            collection_slug = json_dict["collection"]
            asset_slug = json_dict["asset"]
        else:
            collection_slug = self.request.POST.get("collection", None)
            asset_slug = self.request.POST.get("asset", None)

        if collection_slug and asset_slug:
            response = requests.get(
                "%s://%s/ws/collection_asset_random/%s/%s"
                % (self.request.scheme, self.request.get_host(), collection_slug, asset_slug),
                cookies=self.request.COOKIES,
            )
            random_asset_json_val = json.loads(response.content.decode("utf-8"))

            collection = Collection.objects.filter(slug=collection_slug)

            # select a random asset in this collection that has status of EDIT
            asset = (
                Asset.objects.filter(collection=collection[0], status=Status.EDIT)
                .exclude(slug=asset_slug)
                .order_by("?")
                .first()
            )

            return HttpResponse(
                "/transcribe/%s/asset/%s/" % (collection_slug, random_asset_json_val["slug"])
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
            user = json_dict["user"]
            page_url = json_dict["page_url"]
        else:
            user = self.request.POST.get("user", None)
            page_url = self.request.POST.get("page_url", None)

        if user == "AnonymousUser":
            user = "anonymous"

        if user and page_url:
            user_obj = User.objects.filter(username=user).first()

            # update the PageInUse

            change_page_in_use = {"page_url": page_url, "user": user_obj.id}

            requests.put(
                "%s://%s/ws/page_in_use_update/%s/%s/" %
                (

                    self.request.scheme,
                    self.request.get_host(),
                    user_obj.id,
                    page_url
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
    success_url = "."

    def get_initial(self):
        if self.request.GET.get("pre_populate", None) is None:
            return None
        else:
            return {
                'email': (
                    None
                    if self.request.user.is_anonymous
                    else self.request.user.email
                ),
                'link': (
                    self.request.META.get('HTTP_REFERER')
                    if self.request.META.get('HTTP_REFERER') else None
                )
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


class CollectionView(TemplateView):
    template_name = "transcriptions/create.html"

    def post(self, *args, **kwargs):
        self.get_context_data()
        name = self.request.POST.get("name")
        url = self.request.POST.get("url")
        slug = name.replace(" ", "-")

        view = CreateCollectionView.as_view()
        importer_resp = view(self.request, *args, **kwargs)

        return render(self.request, self.template_name, importer_resp.data)


class DeleteCollectionView(TemplateView):
    """
    deletes the collection
    """

    def get(self, request, *args, **kwargs):
        requests.delete("%s://%s/ws/collection_delete/%s/" %
                        (self.request.scheme,
                         self.request.get_host(),
                         self.args[0]),
                        cookies=self.request.COOKIES)

        os.system(
            "rm -rf {0}".format(settings.MEDIA_ROOT + "/concordia/" + self.args[0])
        )
        return redirect("/transcribe/")


class DeleteAssetView(TemplateView):
    """
    Hides an asset with status inactive. Hidden assets do not display in
    asset view. After hiding an asset, page redirects to collection view.
    """

    def get(self, request, *args, **kwargs):
        asset_update = {"collection": self.args[0], "slug": self.args[1]}

        requests.put(
            "%s://%s/ws/asset_update/%s/%s/" %
            (
                self.request.scheme,
                self.request.get_host(),
                self.args[0],
                self.args[1],
            ),
            data=asset_update,
            cookies=self.request.COOKIES,
        )

        return redirect("/transcribe/" + self.args[0] + "/")


class ReportCollectionView(TemplateView):
    """
    Report the collection
    """

    template_name = "transcriptions/report.html"

    def get(self, request, *args, **kwargs):
        collection = Collection.objects.get(slug=self.args[0])
        collection.asset_set.all()
        projects = (
            collection.asset_set.values("title")
            .annotate(
                total=Count("title"),
                in_progress=Count("status", filter=Q(status__in=["25", "75", "50"])),
                complete=Count("status", filter=Q(status="100")),
                tags=Count("userassettagcollection__tags", distinct=True),
                contributors=Count("transcription__user_id", distinct=True),
                not_started=Count("status", filter=Q(status="0")),
            )
            .order_by("title")
        )
        paginator = Paginator(projects, ASSETS_PER_PAGE)

        if not self.request.GET.get("page"):
            page = 1
        else:
            page = self.request.GET.get("page")

        projects = paginator.get_page(page)
        return render(self.request, self.template_name, locals())


class FilterCollections(generics.ListAPIView):
    def get_queryset(self):
        name_query = self.request.query_params.get("name")
        if name_query:
            queryset = Collection.objects.filter(slug__contains=name_query).values_list(
                "slug", flat=True
            )
        else:
            queryset = Collection.objects.all().values_list("slug", flat=True)
        return queryset

    def list(self, request):
        queryset = self.get_queryset()
        from django.http import JsonResponse

        return JsonResponse(list(queryset), safe=False)
