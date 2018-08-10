# TODO: Add copyright header

from datetime import datetime, timedelta
from django.shortcuts import get_object_or_404
from rest_framework import generics, exceptions
from rest_framework.authentication import BasicAuthentication
from rest_framework.response import Response

from .models import PageInUse, User, Collection, Asset, Transcription
from .serializers import PageInUseSerializer, CollectionDetailSerializer, AssetSerializer, \
    TranscriptionSerializer


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
#    queryset = PageInUse.objects.all()
    lookup_field = 'page_url'

    def get_queryset(self):
        return PageInUse.objects.all().filter(page_url=self.kwargs['page_url'])


class PageInUsePut(generics.UpdateAPIView):
    """
    PUT: Update an existing PageInUse
    """
    model = PageInUse
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = PageInUseSerializer
    queryset = PageInUse.objects.all()
    lookup_field = 'page_url'


class CollectionGet(generics.RetrieveAPIView):
    """
    GET: Retrieve an existing Collection
    """
    model = Collection
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = CollectionDetailSerializer
    queryset = Collection.objects.all()
    lookup_field = 'slug'


class CollectionAssetsGet(generics.RetrieveAPIView):
    """
    GET: Retrieve an existing Collection
    """
    model = Collection
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = CollectionDetailSerializer
    queryset = Collection.objects.all()
    lookup_field = 'slug'


class AssetsList(generics.ListAPIView):
    """
    GET: Return Assets by collection
    """
    model = Asset
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = AssetSerializer
    lookup_field = 'collection'

    def get_queryset(self):
        return Asset.objects.filter(collection__slug=self.kwargs['collection']).order_by("title", "sequence")


class PageInUseFilteredGet(generics.ListAPIView):
    """
    GET: Retrieve all existing PageInUse with filtered values
    """
    model = PageInUse
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = PageInUseSerializer
    lookup_field = 'page_url'

    def get_queryset(self):
        """
        This view should return a list of all the PageInUse updated in the last 5 minutes
        by users other than the user arg
        """
        time_threshold = datetime.now() - timedelta(minutes=5)
        return PageInUse.objects.filter(page_url=self.kwargs['page_url'],
                                        updated_on__gt=time_threshold).exclude(user__username=self.kwargs['user'])


class TranscriptionLastGet(generics.RetrieveAPIView):
    """
    GET: Get the last transcription for an asset
    """
    model = Transcription
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = TranscriptionSerializer
    queryset = Transcription.objects.all()
    lookup_field = 'asset'

    def get_object(self):
        """
        Return the 'last' object for the asset_id. (this is the Transcription with the highest is value.)
        :return: Transcription object
        """
        obj = Transcription.objects.filter(asset__id=self.kwargs['asset']).last()
        return obj

