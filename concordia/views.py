
import os
from logging import getLogger

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import TemplateView
from registration.backends.simple.views import RegistrationView

from concordia.forms import ConcordiaUserEditForm, ConcordiaUserForm
from concordia.models import (Asset, Collection, Tag, Transcription,
                              UserAssetTagCollection, UserProfile)

from importer_app.views import CreateCollectionView, get_task_status

logger = getLogger(__name__)

ASSETS_PER_PAGE = 36


def concordia_api(relative_path):
    abs_path = "{}/api/v1/{}".format(settings.CONCORDIA["netloc"], relative_path)
    logger.debug("Calling API path %s", abs_path)
    data = requests.get(abs_path).json()

    logger.debug("Received %s", data)
    return data


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
        collection = Collection.objects.get(slug=self.args[0])
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

    def get_context_data(self, **kws):

        asset = Asset.objects.get(collection__slug=self.args[0], slug=self.args[1])

        transcription = Transcription.objects.filter(
            asset=asset, user_id=self.request.user.id
        )
        if transcription:
            transcription = transcription[0]
        tags = UserAssetTagCollection.objects.filter(
            asset=asset, user_id=self.request.user.id
        )
        if tags:
            tags = tags[0].tags.all()

        return dict(
            super().get_context_data(**kws),
            asset=asset,
            transcription=transcription,
            tags=tags,
        )

    def post(self, *args, **kwargs):
        self.get_context_data()
        asset = Asset.objects.get(collection__slug=self.args[0], slug=self.args[1])
        if "tx" in self.request.POST:
            tx = self.request.POST.get("tx")
            status = self.request.POST.get("status", "25")
            Transcription.objects.update_or_create(
                asset=asset,
                user_id=self.request.user.id,
                defaults={"text": tx, "status": status},
            )
            asset.status = status
            asset.save()
        if "tags" in self.request.POST:
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

        view = CreateCollectionView.as_view()
        importer_app_resp = view(self.request, *args, **kwargs)

        return render(self.request, self.template_name, importer_app_resp.data)

        # return view(self.request, *args, **kwargs)
        # collection_path = os.path.join(settings.MEDIA_ROOT, "concordia", slug)
        # c = Collection.objects.create(title=name, slug=slug, description=name)
        # c.copy_images_to_collection(url, collection_path)
        # c.create_assets_from_filesystem(collection_path)
        # c.is_active = 1
        # c.save()
        # if c:
        #     return redirect(
        #         reverse(
        #             "transcriptions:collection",
        #             args=[slug],
        #             current_app=self.request.resolver_match.namespace,
        #         )
        #     )
        # return render(self.request, self.template_name, {"error": "yes"})


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
