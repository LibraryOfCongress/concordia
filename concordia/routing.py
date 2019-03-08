# mysite/routing.py
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.conf.urls import url
from . import consumers

websocket_urlpatterns = [
    url(r"^ws/asset/(?P<asset_pk>[^/]+)/$", consumers.AssetConsumer)
]

application = ProtocolTypeRouter(
    {
        # (http->django views is added by default)
        "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
    }
)
