from django.urls import re_path

from main.consumer import Consumer

websocket_urlpatterns = [
    re_path(r'api/subscription/(?P<address>[\w+:]+)/$', Consumer.as_asgi()),
]

