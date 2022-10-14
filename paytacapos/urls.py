from django.urls import path
from rest_framework import routers

from .views import (
    BroadcastPaymentView,
    PosDeviceViewSet,
)

router = routers.DefaultRouter()
router.register(r"devices", PosDeviceViewSet, basename="paytacapos-devices")

urlpatterns = router.urls + [
    path('broadcast/', BroadcastPaymentView.as_view(), name="broadcast-pos-payment")
]
