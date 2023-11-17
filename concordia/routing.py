import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls import path

from . import consumers

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concordia.settings")
django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(
            URLRouter([path("ws/asset/asset_updates/", consumers.AssetConsumer)])
        ),
    }
)
