from django.urls import re_path
from .consumers import ExotelMediaConsumer

websocket_urlpatterns = [
    re_path(r"^ws/exotel/(?P<call_id>[^/]+)/$", ExotelMediaConsumer.as_asgi()),
]
