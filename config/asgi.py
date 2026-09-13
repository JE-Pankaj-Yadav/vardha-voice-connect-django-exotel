import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# IMPORTANT:
# Initialize Django before importing voice_agent.routing.
# routing -> consumers -> models requires the Django app registry
# to already be ready. Importing routing first causes:
# django.core.exceptions.AppRegistryNotReady:
# "Apps aren't loaded yet."
from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from voice_agent.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": URLRouter(websocket_urlpatterns),
})
