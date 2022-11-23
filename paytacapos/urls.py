from django.urls import path
from rest_framework import routers

from .views import (
    BroadcastPaymentView,
    PosDeviceViewSet,
    MerchantViewSet,
    BranchViewSet,
)

router = routers.DefaultRouter()
router.register(r"devices", PosDeviceViewSet, basename="paytacapos-devices")
router.register(r"merchants", MerchantViewSet, basename="paytacapos-merchants")
router.register(r"branches", BranchViewSet, basename="paytacapos-branches")

urlpatterns = router.urls + [
    path('broadcast/', BroadcastPaymentView.as_view(), name="broadcast-pos-payment")
]
