
import os
from logging import getLogger

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import Http404, get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import TemplateView
from registration.backends.simple.views import RegistrationView

from concordia.forms import ConcordiaUserEditForm, ConcordiaUserForm
from concordia.models import (
    Asset,
    Collection,
   Status, Tag,
    Transcription,
    UserAssetTagCollection,
    UserProfile
)

logger = getLogger(__name__)

ASSETS_PER_PAGE = 36


def concordia_api(relative_path):
    abs_path = "{}/api/v1/{}".format(settings.CONCORDIA["netloc"], relative_path)
    logger.debug("Calling API path %s", abs_path)
    data = requests.get(abs_path).json()

    logger.debug("Received %s", data)
    return data


def get_anonymous_user():
    """
    Get the user called "anonymous" if it exist. Create the user if it doesn't exist

    This is the default concordia user if someone is working on the site without logging in first.
    :return: User id
    """
    anon_user = User.objects.filter(username="anonymous").first()
    if anon_user is None:
        anon_user = User.objects.create_user(
            username="anonymous",
            email="anonymous@anonymous.com",
            password="concanonymous",
        )
    return anon_user.id


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
            return render(self.request, self.template_name, locals())
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
        return super().get_context_data(
            **dict(
                kws,
                transcriptions=Transcription.objects.filter(
                    user_id=self.request.user.id
                ).order_by("-updated_on"),
                form=ConcordiaUserEditForm(initial=data),
            )
        )


class ConcordiaView(TemplateView):
    template_name = "transcriptions/home.html"

    def get_context_data(self, **kws):
        response = concordia_api("collections/")
        return dict(super().get_context_data(**kws), response=response)


class ConcordiaCollectionView(TemplateView):
    template_name = "transcriptions/collection.html"

    def get_context_data(self, **kws):
        try:
            collection = Collection.objects.get(slug=self.args[0])
        except Collection.DoesNotExist:
            raise Http404
        asset_list = collection.asset_set.all().order_by("title", "sequence")
        paginator = Paginator(asset_list, ASSETS_PER_PAGE)

        if not self.request.GET.get("page"):
            page = 1
        else:
            page = self.request.GET.get("page")

        assets = paginator.get_page(page)

        return dict(
            super().get_context_data(**kws), collection=collection, assets=assets
        )


class ConcordiaAssetView(TemplateView):
    template_name = "transcriptions/asset.html"

    state_dictionary = {
        "Save": Status.EDIT,
        "Submit for Review": Status.SUBMITTED,
        "Mark Completed": Status.COMPLETED,
    }

    def get_context_data(self, **kws):

        asset = Asset.objects.get(collection__slug=self.args[0], slug=self.args[1])

        # Get all transcriptions, they are no longer tied to a specific user
        transcription = Transcription.objects.filter(asset=asset).last()

        # Get all tags, they are no longer tied to a specific user
        db_tags = UserAssetTagCollection.objects.filter(asset=asset)

        tags = all_tags = None
        if db_tags:
            for tags_in_db in db_tags:
                if tags is None:
                    tags = tags_in_db.tags.all()
                    all_tags = tags
                else:
                    pass
                    all_tags = (tags | tags_in_db.tags.all()).distinct()  # merge the querysets

        return dict(
            super().get_context_data(**kws),
            asset=asset,
            transcription=transcription,
            tags=all_tags,
        )

    def post(self, *args, **kwargs):
        self.get_context_data()
        asset = Asset.objects.get(collection__slug=self.args[0], slug=self.args[1])
        if "tx" in self.request.POST:
            tx = self.request.POST.get("tx")
            status = self.state_dictionary[self.request.POST.get("action")]
            # Save all transcriptions, we will need this reports
            Transcription.objects.create(
                asset=asset,
                user_id=self.request.user.id
                if self.request.user.id is not None
                else get_anonymous_user(),
                text=tx,
                status=status,
            )
            asset.status = status
            asset.save()
        if "tags" in self.request.POST and len(self.request.POST.get("tags")) > 0:
            tags = self.request.POST.get("tags").split(",")
            utags, status = UserAssetTagCollection.objects.get_or_create(
                asset=asset, user_id=self.request.user.id
            )
            all_tag = utags.tags.all().values_list("name", flat=True)
            all_tag_list = list(all_tag)
            delete_tags = [i for i in all_tag_list if i not in tags]
            utags.tags.filter(name__in=delete_tags).delete()
            for tag in tags:
                tag_ob, t_status = Tag.objects.get_or_create(name=tag, value=tag)
                if tag_ob not in utags.tags.all():
                    utags.tags.add(tag_ob)

        return redirect(self.request.path)


class TranscriptionView(TemplateView):
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
        collection_path = os.path.join(settings.MEDIA_ROOT, "concordia", slug)
        c = Collection.objects.create(title=name, slug=slug, description=name)
        c.copy_images_to_collection(url, collection_path)
        c.create_assets_from_filesystem(collection_path)
        c.is_active = 1
        c.save()
        if c:
            return redirect(
                reverse(
                    "transcriptions:collection",
                    args=[slug],
                    current_app=self.request.resolver_match.namespace,
                )
            )
        return render(self.request, self.template_name, {"error": "yes"})


class DeleteCollectionView(TemplateView):
    """
    deletes the collection

    """

    def get(self, request, *args, **kwargs):
        print("Deleting:", self.args[0])
        collection = Collection.objects.get(slug=self.args[0])
        collection.asset_set.all().delete()
        collection.delete()
        os.system(
            "rm -rf {0}".format(settings.MEDIA_ROOT + "/concordia/" + collection.slug)
        )
        return redirect("/transcribe/")


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
