# TODO: Add copyright header

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.transaction import atomic
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
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


@method_decorator(never_cache, name="dispatch")
class TagCreate(generics.ListCreateAPIView):
    """
    POST: create or retrieve a tag
    """

    model = Tag
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = TagSerializer
    queryset = Tag.objects.all()

    @atomic
    def post(self, request, *, asset_pk):
        asset = get_object_or_404(Asset, pk=asset_pk)

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

        all_tags_qs = Tag.objects.filter(userassettagcollection__asset__pk=asset_pk)
        all_tags = all_tags_qs.order_by("value")
        all_tags = all_tags.values_list("value", flat=True)

        return Response({"user_tags": tags, "all_tags": all_tags})
