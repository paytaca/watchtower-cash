from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from rest_framework import routers
from main import views

app_name = "main"


router = routers.DefaultRouter()
# router.register(r"slp_address", views.SlpAddressViewSet)
# router.register(r"token", views.TokenViewSet)
# router.register(r"transaction", views.TransactionViewSet)
# router.register(r"auth", views.AuthViewSet,basename='auth')
# path('set-address/', SetAddressView.as_view(), name='setaddress'),

urlpatterns = router.urls

urlpatterns = [
    path(r"/subscription/", views.SubscribeViewSet.as_view(), name='subscribe')
]