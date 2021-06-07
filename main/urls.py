from django.urls import path, re_path
from django.views.decorators.csrf import csrf_exempt
from rest_framework import routers
from main import views
from django.conf.urls import url

app_name = "main"


router = routers.DefaultRouter()
# router.register(r"slp_address", views.SlpAddressViewSet)
# router.register(r"token", views.TokenViewSet)
# router.register(r"transaction", views.TransactionViewSet)
# router.register(r"auth", views.AuthViewSet,basename='auth')
# path('set-address/', SetAddressView.as_view(), name='setaddress'),

main_urls = router.urls

main_urls += [
    re_path(r"^subscription/$", views.SubscribeViewSet.as_view(), name='subscribe'),
    re_path(r"^blockheight/latest/$", views.BlockHeightViewSet.as_view(), name='blockheight'),
    re_path(r"^balance/bch/(?P<bchaddress>[\w+:]+)/$", views.Balance.as_view(),name='bch-balance'),
    re_path(r"^balance/slp/(?P<slpaddress>[\w+:]+)/$", views.Balance.as_view(),name='slp-balance'),
    re_path(r"^balance/slp/(?P<slpaddress>[\w+:]+)/(?P<tokenid>[\w+]+)", views.Balance.as_view(),name='slp-token-balance'),
    re_path(r"^utxo/bch/(?P<bchaddress>[\w+:]+)/$", views.UTXO.as_view(),name='bch-utxo'),
    re_path(r"^utxo/slp/(?P<slpaddress>[\w+:]+)/$", views.UTXO.as_view(),name='slp-utxo'),
    re_path(r"^utxo/slp/(?P<slpaddress>[\w+:]+)/(?P<tokenid>[\w+]+)", views.UTXO.as_view(),name='slp-token-utxo'),
    path('broadcast', views.BroadcastViewSet.as_view(), name="broadcast-transaction")
]

test_urls = [
    re_path(r"^(?P<address>[\w+:]+)/$", views.TestSocket.as_view(),name='testbch'),
    re_path(r"^(?P<address>[\w+:]+)/(?P<tokenid>[\w+]+)", views.TestSocket.as_view(),name='testbch'),
]
