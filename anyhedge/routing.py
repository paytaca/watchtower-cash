from django.urls import re_path

from anyhedge.consumers import AnyhedgeUpdatesConsumer

websocket_urlpatterns = [
    re_path(r'ws/anyhedge/updates/(?P<wallet_hash>[\w+:]+)/$', AnyhedgeUpdatesConsumer.as_asgi()),
]
