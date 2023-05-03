from django.urls import re_path

from rampp2p.consumers import RampP2PUpdatesConsumer

websocket_urlpatterns = [
    re_path(r'ws/ramp-p2p/updates/(?P<wallet_hash>[\w+:]+)/$', RampP2PUpdatesConsumer.as_asgi()),
]
