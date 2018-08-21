# TODO: Add copyright header

from datetime import datetime, timedelta

from django.http import QueryDict
from django.shortcuts import get_object_or_404
from rest_framework import exceptions, generics, status
from rest_framework.authentication import BasicAuthentication
from rest_framework.response import Response

from .models import (Asset, Collection, PageInUse, Status, Tag, Transcription, User,
                     UserAssetTagCollection)
from .serializers import (AssetSerializer, CollectionDetailSerializer,
                          PageInUseSerializer, TagSerializer, TranscriptionSerializer,
                          UserAssetTagSerializer)


class ConcordiaAPIAuth(BasicAuthentication):
    """
    Verify the user's session exists. Even anonymous users are "logged" in, though they are not aware of it.
    """

    def authenticate(self, request):
        # anonymous user does not log in, so test if the user is "anonymous"
        if "user" in request.data:
            user = User.objects.filter(id=request.data["user"])
            if user[0] and user[0].username == "anonymous":
                return user, None
        if not request.session.exists(request.session.session_key):
            raise exceptions.AuthenticationFailed

        return request.session.session_key, None


class PageInUseCreate(generics.CreateAPIView):
    """
    POST: Create a PageInUse value
    """

    model = PageInUse
    authentication_classes = (ConcordiaAPIAuth,)
    queryset = PageInUse.objects.all()
    serializer_class = PageInUseSerializer


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


class CollectionGet(generics.RetrieveAPIView):
    """
    GET: Retrieve an existing Collection by slug value
    """

    model = Collection
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = CollectionDetailSerializer
    queryset = Collection.objects.all()
    lookup_field = "slug"


class CollectionGetById(generics.RetrieveAPIView):
    """
    GET: Retrieve an existing Collection by id
    """

    model = Collection
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = CollectionDetailSerializer
    queryset = Collection.objects.all()
    lookup_field = "id"


class CollectionAssetsGet(generics.RetrieveAPIView):
    """
    GET: Retrieve an existing Collection
    """

    model = Collection
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = CollectionDetailSerializer
    queryset = Collection.objects.all()
    lookup_field = "slug"


class AssetsList(generics.ListAPIView):
    """
    GET: Return Assets by collection
    """

    model = Asset
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = AssetSerializer
    lookup_field = "collection"

    def get_queryset(self):
        return Asset.objects.filter(
            collection__slug=self.kwargs["collection"]
        ).order_by("title", "sequence")


class AssetBySlug(generics.RetrieveAPIView):
    """
    GET: Return Asset by collection and slug
    """

    model = Asset
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = AssetSerializer
    lookup_fields = ("collection", "slug")

    def get_object(self):
        asset = Asset.objects.filter(
            collection__slug=self.kwargs["collection"], slug=self.kwargs["slug"]
        )
        if len(asset) > 0:
            return asset[0]
        else:
            return None


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
        :return: Transcription object
        """
        return Transcription.objects.filter(user_id=self.kwargs["user"]).order_by(
            "-updated_on"
        )


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

        asset = get_object_or_404(Asset, id=request_data["asset"])

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
            collection__slug=request_data["collection"], slug=request_data["asset"]
        )

        utags, status = UserAssetTagCollection.objects.get_or_create(
            asset=asset, user_id=request_data["user_id"]
        )

        tag_ob, t_status = Tag.objects.get_or_create(
            name=request_data["name"], value=request_data["value"]
        )
        if tag_ob not in utags.tags.all():
            utags.tags.add(tag_ob)

        serializer = TagSerializer(data=request_data)
        if serializer.is_valid():
            pass
        return Response(serializer.data)


class TagDelete(generics.DestroyAPIView):
    """
    DELETE: delete a tag
    """

    model = UserAssetTagCollection
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = UserAssetTagSerializer
    queryset = UserAssetTagCollection.objects.all()

    def delete(self, request, *args, **kwargs):
        asset = Asset.objects.get(
            collection__slug=kwargs["collection"], slug=kwargs["asset"]
        )

        user_asset_collection = get_object_or_404(
            UserAssetTagCollection, asset=asset, user_id=kwargs["user_id"]
        )

        user_asset_collection.tags.filter(name=kwargs["name"]).delete()

        serializer = UserAssetTagSerializer(data=kwargs)
        if serializer.is_valid():
            pass
        return Response(serializer.data)
