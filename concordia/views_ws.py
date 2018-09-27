# TODO: Add copyright header

from datetime import datetime, timedelta

from django.core.exceptions import ObjectDoesNotExist
from django.http import QueryDict
from django.shortcuts import get_object_or_404
from rest_framework import exceptions, generics, status, permissions
from rest_framework.authentication import BasicAuthentication
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response

from .models import (
    Asset,
    Campaign,
    Item,
    PageInUse,
    Status,
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
    PageInUseSerializer,
    TagSerializer,
    TranscriptionSerializer,
    UserAssetTagSerializer,
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


class PageInUseCreate(generics.CreateAPIView):
    """
    POST: Create a PageInUse value
    """

    model = PageInUse
    authentication_classes = (ConcordiaAPIAuth,)
    queryset = PageInUse.objects.all()
    serializer_class = PageInUseSerializer


class PageInUseDelete(generics.DestroyAPIView):
    """
    DELETE: Delete a PageInUse value
    """

    model = PageInUse
    authentication_classes = (ConcordiaAPIAuth,)
    queryset = PageInUse.objects.all()
    serializer_class = PageInUseSerializer
    lookup_field = "page_url"


class PageInUseGet(generics.RetrieveUpdateAPIView):
    """
    GET: Get a PageInUse value
    PUT: Update a PageInUse value
    """

    model = PageInUse
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = PageInUseSerializer
    lookup_field = "page_url"

    def get_queryset(self):
        return PageInUse.objects.all().filter(page_url=self.kwargs["page_url"])


class PageInUseUserGet(generics.RetrieveUpdateAPIView):
    """
    GET: Get a PageInUse value for user
    PUT: Update a PageInUse value
    """

    model = PageInUse
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = PageInUseSerializer
    #    queryset = PageInUse.objects.all()
    lookup_fields = ("page_url", "user")

    def get_object(self):
        return (
            PageInUse.objects.all()
            .filter(page_url=self.kwargs["page_url"], user__id=self.kwargs["user"])
            .last()
        )


class PageInUseCount(generics.RetrieveAPIView):
    """
    GET: Return True if the page is in use by a different user, otherwise False
    """

    model = PageInUse
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = PageInUseSerializer
    queryset = PageInUse.objects.all()
    lookup_fields = ("page_url", "user")

    def get(self, request, *args, **kwargs):
        time_threshold = datetime.now() - timedelta(minutes=5)
        page_in_use_count = (
            PageInUse.objects.filter(
                page_url=self.kwargs["page_url"], updated_on__gt=time_threshold
            )
            .exclude(user__id=self.kwargs["user"])
            .count()
        )

        if page_in_use_count > 0:
            return Response(data={"page_in_use": True})
        else:
            return Response(data={"page_in_use": False})


class PageInUsePut(generics.UpdateAPIView):
    """
    PUT: Update an existing PageInUse
    """

    model = PageInUse
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = PageInUseSerializer
    queryset = PageInUse.objects.all()
    lookup_field = "page_url"

    def put(self, request, *args, **kwargs):
        if type(request.data) == QueryDict:
            # when using APIFactory to submit post, data must be converted from QueryDict
            request_data = request.data.dict()
        else:
            request_data = request.data

        request_data["updated_on"] = datetime.now()
        page_in_use = PageInUse.objects.get(
            page_url=request_data["page_url"], user_id=request_data["user"]
        )
        page_in_use.updated_on = datetime.now()
        page_in_use.save()

        serializer = PageInUseSerializer(data=request_data)
        if serializer.is_valid():
            pass
        return Response(serializer.data)


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


class AssetRandomInCampaign(generics.RetrieveAPIView):
    """
    GET: Return a random asset from the campaign excluding the passed in asset slug
    """

    model = Asset
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = AssetSerializer
    lookup_fields = ("campaign", "slug")

    def get_object(self):
        try:
            return (
                Asset.objects.filter(
                    campaign__slug=self.kwargs["campaign"], status=Status.EDIT
                )
                .exclude(slug=self.kwargs["slug"])
                .order_by("?")
                .first()
            )
        except ObjectDoesNotExist:
            return None


class AssetUpdate(generics.UpdateAPIView):
    """
    PUT: Update an Asset
    """

    model = Campaign
    authentication_classes = (ConcordiaAPIAuth,)
    permission_classes = (ConcordiaAdminPermission,)
    queryset = Campaign.objects.all()
    serializer_class = CampaignDetailSerializer
    lookup_fields = ("campaign", "slug")

    def put(self, request, *args, **kwargs):
        if type(request.data) == QueryDict:
            # when using APIFactory to submit post, data must be converted from QueryDict
            request_data = request.data.dict()
        else:
            request_data = request.data

        campaign = Campaign.objects.get(slug=request_data["campaign"])

        # FIXME: use .update for performance
        # FIXME: do validation before updating
        asset = Asset.objects.get(slug=request_data["slug"], campaign=campaign)
        asset.status = Status.INACTIVE
        asset.save()

        serializer = CampaignDetailSerializer(data=request_data)
        # FIXME: do something when validation fails
        if serializer.is_valid():
            pass

        return Response(serializer.data)


class PageInUseFilteredGet(generics.ListAPIView):
    """
    GET: Retrieve all existing PageInUse with filtered values
    """

    model = PageInUse
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = PageInUseSerializer
    lookup_field = "page_url"

    def get_queryset(self):
        """
        This view should return a list of all the PageInUse updated in the last 5 minutes
        by users other than the user arg
        """
        time_threshold = datetime.now() - timedelta(minutes=5)
        page = PageInUse.objects.filter(
            page_url=self.kwargs["page_url"], updated_on__gt=time_threshold
        ).exclude(user__username=self.kwargs["user"])
        return page


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
        return Transcription.objects.filter(user_id=self.kwargs["user"]).order_by(
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

    def post(self, request, *args, **kwargs):
        if type(request.data) == QueryDict:
            # when using APIFactory to submit post, data must be converted from QueryDict
            request_data = request.data.dict()
        else:
            request_data = request.data

        asset = get_object_or_404(Asset, slug=request_data["asset"])

        transcription = Transcription.objects.create(
            asset=asset,
            user_id=request_data["user_id"],
            text=request_data["text"],
            status=request_data["status"],
        )

        serializer = TranscriptionSerializer(data=request_data)
        if serializer.is_valid():
            pass
        return Response(serializer.data, status=status.HTTP_201_CREATED)


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
        db_tags = UserAssetTagCollection.objects.filter(asset__id=self.kwargs["asset"])

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

    def post(self, request, *args, **kwargs):
        if type(request.data) == QueryDict:
            # when using APIFactory to submit post, data must be converted from QueryDict
            request_data = request.data.dict()
        else:
            request_data = request.data

        asset = Asset.objects.get(
            campaign__slug=request_data["campaign"], slug=request_data["asset"]
        )

        utags, status = UserAssetTagCollection.objects.get_or_create(
            asset=asset, user_id=request_data["user_id"]
        )

        tag_ob, t_status = Tag.objects.get_or_create(value=request_data["value"])
        if tag_ob not in utags.tags.all():
            utags.tags.add(tag_ob)

        serializer = TagSerializer(data=request_data)
        if serializer.is_valid():
            pass
        return Response(serializer.data)
