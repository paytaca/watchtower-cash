from django.urls import re_path

from purelypeer.consumers import *


websocket_urlpatterns = [
    re_path(r'ws/vouchers/(?P<merchant_address>[\w+:]+)/$', VoucherConsumer.as_asgi()),
]
