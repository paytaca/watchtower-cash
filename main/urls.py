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
    path(r"subscription/", views.SubscribeViewSet.as_view(), name='subscribe')
]


test_urls = [
    re_path(r"^(?P<address>[\w+:]+)/$", views.TestSocket.as_view(),name='testbch'),
    re_path(r"^(?P<address>[\w+:]+)/(?P<tokenid>[\w+]+)", views.TestSocket.as_view(),name='testbch'),
]