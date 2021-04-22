from django.urls import re_path

from main.consumer import *

websocket_urlpatterns = [
    re_path(r'ws/socket/(?P<address>\w+)/$', Consumer.as_asgi()),
]
