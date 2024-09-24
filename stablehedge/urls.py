from rest_framework import routers

from .views import (
    RedemptionContractViewSet,
    FiatTokenViewSet,
)

router = routers.DefaultRouter()
router.register(r"redemption-contracts", RedemptionContractViewSet, basename="redemption-contracts")
router.register(r"fiat-tokens", FiatTokenViewSet, basename="fiat-tokens")

urlpatterns = router.urls + [
]
