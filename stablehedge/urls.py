from rest_framework import routers

from .views import (
    RedemptionContractViewSet,
    TreasuryContractViewSet,
    FiatTokenViewSet,
    TestUtilsViewSet,
)

router = routers.DefaultRouter()
router.register(r"redemption-contracts", RedemptionContractViewSet, basename="redemption-contracts")
router.register(r"treasury-contracts", TreasuryContractViewSet, basename="treasury-contracts")
router.register(r"fiat-tokens", FiatTokenViewSet, basename="fiat-tokens")
router.register(r"test-utils", TestUtilsViewSet, basename="test-utils")

urlpatterns = router.urls + [
]
