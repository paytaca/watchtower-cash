from django.urls import re_path

from rampp2p.consumers import RampP2PUpdatesConsumer

websocket_urlpatterns = [
    re_path(r'ws/ramp-p2p/updates/order/(?P<order_id>[\w+:]+)/$', RampP2PUpdatesConsumer.as_asgi()),
    re_path(r'ws/ramp-p2p/updates/market-price', RampP2PUpdatesConsumer.as_asgi()),
]
