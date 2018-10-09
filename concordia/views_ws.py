# TODO: Add copyright header

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db.transaction import atomic
from django.shortcuts import get_object_or_404
from rest_framework import exceptions, generics, permissions, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response

from .models import (
    Asset,
    Campaign,
    Item,
    Tag,
    Transcription,
    User,
    UserAssetTagCollection,
    UserProfile,
)
from .serializers import (
    AssetSerializer,
    CampaignDetailSerializer,
    ItemSerializer,
    TagSerializer,
    TranscriptionSerializer,
    UserProfileSerializer,
    UserSerializer,
)
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


class ConcordiaAdminPermission(permissions.BasePermission):
    """
    Verify the user is an admin. Called for any action to db that is not a Retrieve
    """

    def has_permission(self, request, view):
        # always allow GET method
        if request.method in permissions.SAFE_METHODS:
            return True

        if not request.session.exists(request.session.session_key):
            return False

        try:
            user = User.objects.get(id=request.session._session["_auth_user_id"])
            return user.is_superuser
        except ObjectDoesNotExist:
            return False


class UserProfileGet(generics.RetrieveAPIView):
    """
    GET: Return a user profile
    """

    model = UserProfile
    authentication_classes = (ConcordiaAPIAuth,)
    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializer
    lookup_field = "user_id"

    def get_object(self):
        try:
            user = User.objects.get(id=int(self.kwargs["user_id"]))
            return UserProfile.objects.get(user=user)
        except ObjectDoesNotExist:
            return None


class UserGet(generics.RetrieveAPIView):
    """
    GET: Return a User
    """

    model = User
    authentication_classes = (ConcordiaAPIAuth,)
    queryset = User.objects.all()
    serializer_class = UserSerializer
    lookup_field = "user_name"

    def get_object(self):
        try:
            return User.objects.get(username=self.kwargs["user_name"])
        except ObjectDoesNotExist:
            return None


class CampaignGet(generics.RetrieveAPIView):
    """
    GET: Retrieve an existing Campaign by slug value
    """

    model = Campaign
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = CampaignDetailSerializer
    queryset = Campaign.objects.all()
    lookup_field = "slug"


class CampaignGetById(generics.RetrieveAPIView):
    """
    GET: Retrieve an existing Campaign by id
    """

    model = Campaign
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = CampaignDetailSerializer
    queryset = Campaign.objects.all()
    lookup_field = "id"


class CampaignAssetsGet(generics.RetrieveAPIView):
    """
    GET: Retrieve an existing Campaign
    """

    model = Campaign
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = CampaignDetailSerializer
    queryset = Campaign.objects.all()
    lookup_field = "slug"


class ItemGetById(generics.RetrieveAPIView):
    """
    GET: Retrieve assets for one item
    """

    model = Item
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = ItemSerializer
    lookup_field = "item_id"

    def get_queryset(self):
        return Item.objects.filter(slug=self.kwargs["item_id"])


class AssetsList(generics.ListAPIView):
    """
    GET: Return Assets by campaign
    """

    model = Asset
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = AssetSerializer
    lookup_field = "campaign"

    def get_queryset(self):
        return Asset.objects.filter(campaign__slug=self.kwargs["campaign"]).order_by(
            "title", "sequence"
        )


class AssetBySlug(generics.RetrieveAPIView):
    """
    GET: Return Asset by campaign and slug
    """

    model = Asset
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = AssetSerializer
    lookup_fields = ("campaign", "slug")

    def get_object(self):
        asset = Asset.objects.filter(
            campaign__slug=self.kwargs["campaign"], slug=self.kwargs["slug"]
        )
        if len(asset) > 0:
            return asset[0]
        else:
            return None


class TranscriptionLastGet(generics.RetrieveAPIView):
    """
    GET: Get the last transcription for an asset
    """

    model = Transcription
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = TranscriptionSerializer
    queryset = Transcription.objects.all()
    lookup_field = "asset"

    def get_object(self):
        """
        Return the 'last' object for the asset_id. (this is the Transcription with the highest is value.)
        :return: Transcription object
        """
        obj = Transcription.objects.filter(asset__id=self.kwargs["asset"]).last()
        return obj


class TranscriptionByUser(generics.ListAPIView):
    """
    GET: Get the transcriptions for a user id
    """

    model = Transcription
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = TranscriptionSerializer
    queryset = Transcription.objects.all()
    lookup_field = "user"

    def get_queryset(self):
        """
        Return the user's transcriptions
        :return: Transcription object list
        """
        return Transcription.objects.filter(user=self.request.user).order_by(
            "-updated_on"
        )


class TranscriptionByAsset(generics.ListAPIView):
    """
    GET: Get the transcriptions for an asset
    """

    model = Transcription
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = TranscriptionSerializer
    queryset = Transcription.objects.all()
    lookup_field = "asset_slug"

    def get_queryset(self):
        """
        Return the transcriptions for an asset
        :return: Transcription object list
        """
        return Transcription.objects.filter(
            asset__slug=self.kwargs["asset_slug"]
        ).order_by("-updated_on")


class TranscriptionCreate(generics.CreateAPIView):
    """
    POST: Create a new Transcription
    """

    model = Transcription
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = TranscriptionSerializer
    queryset = Transcription.objects.all()

    def post(self, request, *, asset_pk):
        asset = get_object_or_404(Asset, pk=asset_pk)

        partial_data = {
            k: v
            for k, v in request.data.items()
            if k in ("text", "status", "csrftoken")
        }

        serializer = TranscriptionSerializer(data=partial_data, partial=True)
        if serializer.is_valid():
            transcription = Transcription(
                asset=asset,
                user=request.user,
                text=request.data["text"],
                status=request.data["status"],
            )
            transcription.full_clean()
            transcription.save()
        else:
            raise exceptions.ValidationError(serializer.errors)

        full_serialization = TranscriptionSerializer(
            transcription, context={"request": request}
        ).data

        return Response(full_serialization, status=status.HTTP_201_CREATED)


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
