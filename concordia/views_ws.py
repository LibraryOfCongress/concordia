# TODO: Add copyright header

from rest_framework import generics, exceptions
from rest_framework.authentication import BasicAuthentication

from .models import PageInUse, User
from .serializers import PageInUseSerializer


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
    """
    model = PageInUse
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = PageInUseSerializer
#    queryset = PageInUse.objects.all()
    lookup_field = 'page_url'

    def get_queryset(self):
        return PageInUse.objects.all().filter(page_url=self.kwargs['page_url'])

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.page_url = request.data.get("page_url")
        instance.save()
        serializer = self.get_serializer(instance)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return instance


class PageInUsePut(generics.UpdateAPIView):
    """
    PUT: Update an existing PageInUse
    """
    model = PageInUse
    authentication_classes = (ConcordiaAPIAuth,)
    serializer_class = PageInUseSerializer
#    queryset = PageInUse.objects.all()
    lookup_field = 'page_url'

    def get_queryset(self):
        return PageInUse.objects.all().filter(page_url=self.kwargs['page_url'])

    # def update(self, request, *args, **kwargs):
    #     instance = self.get_object()
    #     instance.page_url = request.data.get("page_url")
    #     instance.save()
    #     serializer = self.get_serializer(instance)
    #     serializer.is_valid(raise_exception=True)
    #     self.perform_update(serializer)
    #     return super(PageInUsePut, self).update(request, *args, **kwargs)
