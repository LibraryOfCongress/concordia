"""
ASGI entrypoint — see https://channels.readthedocs.io/en/latest/asgi.html
"""

import django
from channels.routing import get_default_application

django.setup()

application = get_default_application()
