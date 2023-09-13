from django.urls import re_path

from .views import *

urlpatterns = [
    re_path(r"^utxos/(?P<address>[\w+:]+)/$", AddressUtxos.as_view(),name='cts-address-utxo'),
]
