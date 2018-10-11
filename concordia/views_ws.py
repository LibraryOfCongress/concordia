# TODO: Add copyright header

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.transaction import atomic
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response

from .models import Asset, Tag, UserAssetTagCollection
from .serializers import TagSerializer
from .views import get_anonymous_user


class ConcordiaAPIAuth(SessionAuthentication):
    """
    Verify the user's session exists. Even anonymous users are "logged" in,
    though they are not aware of it.
    """

    def authenticate(self, request):
        res = super().authenticate(request)
        if res is None:
            return (get_anonymous_user(), None)
        else:
            return res


class UserAssetTagsGet(generics.ListAPIView):
    """
    Get all tags for an asset
    """

    model = UserAssetTagCollection
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = TagSerializer
    queryset = UserAssetTagCollection.objects.all()
    lookup_field = "asset"

    def get_queryset(self):
        db_tags = UserAssetTagCollection.objects.filter(
            asset__pk=self.kwargs["asset_pk"]
        )

        tags = all_tags = None
        if db_tags:
            for tags_in_db in db_tags:
                if tags is None:
                    tags = tags_in_db.tags.all()
                    all_tags = tags
                else:
                    all_tags = (
                        tags | tags_in_db.tags.all()
                    ).distinct()  # merge the querysets

        if all_tags:
            return all_tags
        else:
            return UserAssetTagCollection.objects.filter(asset__id=-1)


class TagCreate(generics.ListCreateAPIView):
    """
    POST: create or retrieve a tag
    """

    model = Tag
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = TagSerializer
    queryset = Tag.objects.all()

    @atomic
    def post(self, request, *, pk):
        asset = get_object_or_404(Asset, pk=pk)

        if request.user.username == "anonymous":
            raise PermissionDenied()

        user_tags, created = UserAssetTagCollection.objects.get_or_create(
            asset=asset, user=request.user
        )

        tags = set(request.data.getlist("tags"))
        existing_tags = Tag.objects.filter(value__in=tags)
        new_tag_values = tags.difference(i.value for i in existing_tags)
        new_tags = [Tag(value=i) for i in new_tag_values]
        try:
            for i in new_tags:
                i.full_clean()
        except ValidationError as exc:
            return Response({"error": exc.messages}, status=400)

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

        all_tags_qs = Tag.objects.filter(userassettagcollection__asset__pk=pk)
        all_tags = all_tags_qs.values_list("value", flat=True)

        return Response({"user_tags": tags, "all_tags": all_tags})
