from django.urls import re_path

from rampp2p.consumers import *

websocket_urlpatterns = [
    re_path(r'ws/ramp-p2p/subscribe/order/(?P<order_id>[\w+:]+)/$', OrderUpdatesConsumer.as_asgi()),
    re_path(r'ws/ramp-p2p/subscribe/market-price/(?P<currency>[\w+:]+)/$', MarketRateConsumer.as_asgi()),
    re_path(r'ws/ramp-p2p/subscribe/general/(?P<wallet_hash>[\w+:]+)/$', GeneralUpdatesConsumer.as_asgi()),
    re_path(r'ws/ramp-p2p/subscribe/(?P<wallet_hash>[\w+:]+)/cash-in/$', CashinAlertsConsumer.as_asgi()),
]
