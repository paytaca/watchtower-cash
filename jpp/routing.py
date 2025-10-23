from django.urls import re_path
from jpp.consumer import InvoicePaymentConsumer


websocket_urlpatterns = [
    re_path(r'ws/jpp/invoice/(?P<invoice_uuid>[0-9a-f]+)/$', InvoicePaymentConsumer.as_asgi()),
]

