from django.urls import re_path

from stablehedge.consumer import StablehedgeRpcConsumer

websocket_urlpatterns = [
    re_path(r'ws/stablehedge/rpc/', StablehedgeRpcConsumer.as_asgi()),
]
