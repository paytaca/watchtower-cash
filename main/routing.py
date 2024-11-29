from django.urls import re_path

from main.consumer import Consumer
from smartbch.consumer import TransactionTransferUpdatesConsumer
from paytacapos.consumer import PaytacaPosUpdatesConsumer

websocket_urlpatterns = [
    re_path(r'ws/watch/address/(?P<address>[\w+:]+)/$', Consumer.as_asgi()),
    re_path(r'ws/watch/wallet/(?P<wallet_hash>[\w+:]+)/$', Consumer.as_asgi()),
    re_path(
        r'ws/paytacapos/updates/(?P<wallet_hash>[\w+:]+)/((?P<posid>[\d+]+)/)?$',
        PaytacaPosUpdatesConsumer.as_asgi(),
    ),


    ###############################
    # Old endpoints for deprecation
    ###############################

    re_path(r'ws/watch/bch/(?P<address>[\w+:]+)/$', Consumer.as_asgi()),  # Currently most used
    re_path(r'ws/watch/slp/(?P<address>[\w+:]+)/$', Consumer.as_asgi()),
    re_path(r'ws/watch/slp/(?P<address>[\w+:]+)/(?P<tokenid>[\w+]+)/', Consumer.as_asgi()),
    re_path(
        r'ws/watch/smartbch/(?P<address>[\w+:]+)/$',
        TransactionTransferUpdatesConsumer.as_asgi(),
    ),
    re_path(
        r'ws/watch/smartbch/(?P<address>[\w+:]+)/(?P<contract_address>[\w+]+)/$',
        TransactionTransferUpdatesConsumer.as_asgi(),
    ),
]

