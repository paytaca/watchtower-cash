from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(
        r'ws/nostr/updates/(?P<wallet_hash>[^/]+)/$',
        consumers.NostrUpdatesConsumer.as_asgi(),
    ),
]

