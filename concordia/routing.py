from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path

from . import consumers

application = ProtocolTypeRouter(
    {
        # (http->django views is added by default)
        "websocket": AuthMiddlewareStack(
            URLRouter([path("ws/asset/asset_updates/", consumers.AssetConsumer)])
        )
    }
)
