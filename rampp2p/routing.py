from django.urls import re_path

from rampp2p.consumers import OrderUpdatesConsumer, MarketRateConsumer

websocket_urlpatterns = [
    re_path(r'ws/ramp-p2p/updates/order/(?P<order_id>[\w+:]+)/$', OrderUpdatesConsumer.as_asgi()),
    re_path(r'ws/ramp-p2p/updates/market-price', MarketRateConsumer.as_asgi()),
]
