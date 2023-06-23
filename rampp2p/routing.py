from django.urls import re_path

from rampp2p.consumers import OrderUpdatesConsumer, MarketPriceConsumer

websocket_urlpatterns = [
    re_path(r'ws/ramp-p2p/updates/order/(?P<order_id>[\w+:]+)/$', OrderUpdatesConsumer.as_asgi()),
    re_path(r'ws/ramp-p2p/updates/market-price', MarketPriceConsumer.as_asgi()),
]
